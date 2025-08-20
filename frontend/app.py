import streamlit as st
import requests
import os
import base64
import json
import traceback
import logging
import google.oauth2.id_token
import google.auth.transport.requests


# --- Configuration ---
# The backend URL will be injected as an environment variable in Cloud Run
BACKEND_URL = os.environ.get("BACKEND_URL", "http://localhost:8000")
AUDIENCE = os.environ.get("AUDIENCE", "")
API_URL = f"{BACKEND_URL}/api/noauth"

logging.basicConfig(level=logging.INFO)


# --- IAP Header Extraction ---
def get_iap_jwt():
    """
    Retrieves the IAP JWT from the request headers.
    
    This function attempts to access the header injected by IAP. It will
    only be present when the app is deployed behind IAP.
    """
    try:
        # st.context was introduced to provide a stable API for this
        headers = st.context.headers
        return headers.get("x-goog-iap-jwt-assertion")
    except Exception:
        # This will fail when running locally or if headers are not available
        return None

def get_backend_iap_jwt():
    """
    Retrieves the IAP JWT from the request headers and generates a new
    token for the backend.
    """
    try:
        logging.info(f"Attempting to fetch token for audience: {AUDIENCE}")
        auth_req = google.auth.transport.requests.Request()
        id_token = google.oauth2.id_token.fetch_id_token(auth_req, AUDIENCE)
        
        if not id_token:
            logging.error("fetch_id_token returned a None or empty value.")
        else:
            logging.info("Successfully fetched ID token.")
            
        return id_token
    except Exception as e:
        logging.error(f"An exception occurred while trying to fetch the ID token: {e}", exc_info=True)
        return None

def display_jwt_info(iap_jwt):
    """Decodes and displays the contents of the IAP JWT for debugging."""
    if iap_jwt:
        with st.expander("View JWT Details (for debugging)"):
            st.subheader("Raw JWT Token")
            st.text_area("JWT", iap_jwt, height=150)
            st.caption("This is the raw, encoded JWT sent by IAP. It is passed to the backend in the Authorization header.")

            st.subheader("Decoded JWT Claims")
            try:
                # JWTs are composed of three parts, separated by dots.
                # The middle part is the payload.
                _, payload, _ = iap_jwt.split('.')
                
                # The payload is Base64Url-encoded. We need to add padding
                # and decode it.
                decoded_payload = base64.urlsafe_b64decode(payload + '==')
                jwt_claims = json.loads(decoded_payload)
                
                st.json(jwt_claims)
                st.caption("This is the decoded payload of the JWT. It contains user information and token details.")
            except Exception as e:
                st.error(f"Could not decode JWT: {e}")


# --- Main App Logic ---
st.title("️🤖 Secure AI Agent")
st.caption("Powered by Vertex AI Search and secured with IAP")

# Initialize chat history and conversation ID in session state
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "Hello! How can I help you today?"}
    ]
if "conversation_id" not in st.session_state:
    st.session_state.conversation_id = None

# Display chat messages from history
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# Get IAP token for backend authentication
iap_jwt = get_iap_jwt()

# Display the decoded JWT information if it exists
display_jwt_info(iap_jwt)

# React to user input
if prompt := st.chat_input("Ask a question..."):
    # Display user message in chat message container
    st.chat_message("user").markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # When running locally, iap_jwt will be None.
    if not iap_jwt:
        st.warning("This app is running in local mode. Backend calls are disabled.")
        response_text = "I am in local mode. I cannot connect to the backend."
    else:
        headers = {"Authorization": f"Bearer {iap_jwt}"}
        payload = {
            "query": prompt,
            "conversation_id": st.session_state.conversation_id
        }
        
        logging.info(f"Sending request to backend API at {API_URL}")
        logging.debug(f"Request payload: {payload}") # Use debug for more verbose info

        with st.spinner("Thinking..."):
            try:
                response = requests.post(API_URL, headers=headers, json=payload)
                response.raise_for_status()  # Raise an exception for bad status codes
                
                response_data = response.json()
                response_text = response_data.get("reply", "No reply found.")
                
                logging.info(f"Successfully received response from backend. Status: {response.status_code}")
                logging.debug(f"Response JSON: {response_data}")

                # Update the conversation ID for the next turn
                st.session_state.conversation_id = response_data.get("conversation_id")
                logging.info(f"Updated conversation ID to: {st.session_state.conversation_id}")

            except requests.exceptions.RequestException as e:
                # Log the exception with stack trace before showing it in the UI
                logging.error("An exception occurred while connecting to the backend.", exc_info=True)
                
                # Now displays the full stack trace in an expander
                st.error(f"Error connecting to backend: {e}")
                with st.expander("View Full Error Trace"):
                    st.code(traceback.format_exc())
                response_text = "An error occurred. Please check the details above."

    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        st.markdown(response_text)
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": response_text})