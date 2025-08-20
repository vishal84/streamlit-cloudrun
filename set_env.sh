#!/bin/bash

export PROJECT_NUMBER=$(gcloud projects describe $(gcloud config get-value project) --format='value(projectNumber)')
export PROJECT_ID=$(gcloud config get-value project)
