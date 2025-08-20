import os
import uuid
import google.auth
import base64
import json
from typing import Optional
from google.auth.transport.requests import Request
from google.oauth2 import id_token
from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer
from google.cloud import discoveryengine_v1alpha
from pydantic import BaseModel

# --- Configuration ---
PROJECT_ID = os.environ.get("GCP_PROJECT_NUMBER") # UPDATED
LOCATION = "global"
DATA_STORE_ID = os.environ.get("VERTEX_AI_DATASTORE_ID")

# --- FastAPI App Initialization ---
app = FastAPI()
auth_scheme = HTTPBearer()

# --- In-memory store for conversation history ---
conversation_history = {}

# --- Pydantic Models ---
class QueryRequest(BaseModel):
    query: str
    conversation_id: Optional[str] = None

class QueryResponse(BaseModel):
    reply: str
    conversation_id: str

# --- IAP JWT Validation ---
def validate_iap_jwt(token: dict = Depends(auth_scheme)) -> str:
    """Validates an IAP-signed JWT."""
    try:
        iap_jwt = token.credentials
        expected_audience = os.environ.get("AUDIENCE")
        if not expected_audience:
            raise ValueError("AUDIENCE environment variable not set.")

        decoded_token = id_token.verify_oauth2_token(
            iap_jwt, Request(), audience=expected_audience
        )
        return decoded_token.get("email", "unknown_email")
    except Exception as e:
        print(f"Error validating IAP JWT: {e}")
        raise HTTPException(
            status_code=401,
            detail="Invalid or missing IAP authorization token.",
        )

# --- Vertex AI Conversational Search Logic ---
def converse_chat_with_followups(query: str, conversation_name: Optional[str] = None):
    """
    Handles a single turn of a multi-turn conversation with Vertex AI Search.
    Uses the ConversationalSearchServiceClient to maintain conversation context.
    """
    if not all([PROJECT_ID, LOCATION, DATA_STORE_ID]):
        raise ValueError("PROJECT_ID, LOCATION, and DATASTORE_ID must be set.")

    client_options = (
        ClientOptions(api_endpoint=f"{LOCATION}-discoveryengine.googleapis.com")
        if LOCATION != "global"
        else None
    )

    # Use the ConversationalSearchServiceClient for multi-turn conversations
    client = discoveryengine_v1alpha.ConversationalSearchServiceClient(client_options=client_options)

    # If conversation_name is not provided, this is the first turn - create new conversation
    if not conversation_name:
        # Use datastore path for conversation creation
        parent = f"projects/{PROJECT_ID}/locations/{LOCATION}/collections/default_collection/dataStores/{DATA_STORE_ID}"
        
        try:
            conversation = client.create_conversation(
                parent=parent, 
                conversation=discoveryengine_v1alpha.Conversation()
            )
            conversation_name = conversation.name
        except Exception as e:
            print(f"Error creating conversation: {e}")
            # Return error immediately if conversation creation fails
            return {
                "summary": f"Unable to start conversation: {str(e)}",
                "results": [],
                "conversation_name": None
            }

    serving_config = client.serving_config_path(
        project=PROJECT_ID,
        location=LOCATION,
        data_store=DATA_STORE_ID,
        serving_config="default_config",
    )

    # Build the conversation request
    request_payload = discoveryengine_v1alpha.ConverseConversationRequest(
        name=conversation_name,
        query=discoveryengine_v1alpha.TextInput(input=query),
        serving_config=serving_config,
        summary_spec=discoveryengine_v1alpha.SearchRequest.ContentSearchSpec.SummarySpec(
            summary_result_count=5,
            include_citations=True,
        ),
    )

    try:
        # Send the conversation request
        response = client.converse_conversation(request=request_payload)
        summary = response.reply.summary.summary_text if response.reply.summary else "No summary available"

        return summary, response.conversation.name if response.conversation else conversation_name
        
    except Exception as e:
        print(f"Error during Vertex AI Search conversation: {e}")
        # Return error but preserve conversation context
        return f"Sorry, I encountered an error: {str(e)}. Please try again.", conversation_name

# --- API Endpoint ---
@app.post("/api/query", response_model=QueryResponse)
async def handle_query(query_request: QueryRequest, user_email: str = Depends(validate_iap_jwt)):
    """
    Handles an incoming conversational query from the frontend.
    """
    print(f"Received query from authenticated user: {user_email}")

    reply_text, conversation_id = converse_chat_with_followups(
        query_request.query, query_request.conversation_id
    )

    return QueryResponse(reply=reply_text, conversation_id=conversation_id)

# --- Updated Authenticated API Endpoint for Echo ---
@app.get("/api/echo")
async def handle_echo(query: str, token: dict = Depends(auth_scheme), user_email: str = Depends(validate_iap_jwt)):
    """
    An authenticated endpoint that echoes the provided query and returns
    details of the IAP JWT used to call it.
    """
    print(f"Received authenticated echo request from: {user_email}")

    raw_jwt = token.credentials
    decoded_header = {}
    decoded_payload = {}

    try:
        header, payload, signature = raw_jwt.split('.')
        # Add padding and decode the header and payload
        decoded_header = json.loads(base64.urlsafe_b64decode(header + '==').decode('utf-8'))
        decoded_payload = json.loads(base64.urlsafe_b64decode(payload + '==').decode('utf-8'))
    except Exception as e:
        print(f"Could not decode JWT: {e}")
        # If decoding fails, we'll return empty objects for the decoded parts
        pass

    return {
        "echo": query,
        "jwt_details": {
            "raw_token": raw_jwt,
            "decoded_header": decoded_header,
            "decoded_payload": decoded_payload
        }
    }

# --- Unauthenticated API Endpoint for Curl Testing ---
@app.post("/api/noauth", response_model=QueryResponse)
async def handle_noauth(query_request: QueryRequest):
    """
    Handles a conversational query from curl for easy testing.
    This endpoint is unauthenticated.
    """
    user_email = "curl-test-user@example.com"
    print(f"Received query from unauthenticated curl user: {user_email}")

    reply_text, conversation_id = converse_chat_with_followups(
        query_request.query, query_request.conversation_id
    )

    return QueryResponse(reply=reply_text, conversation_id=conversation_id)
