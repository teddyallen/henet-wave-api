# Deploy to Google Cloud Run

```bash
PROJECT_ID=your-project-id
REGION=us-central1
SERVICE=henet-wave-api

gcloud builds submit --tag gcr.io/$PROJECT_ID/$SERVICE

gcloud run deploy $SERVICE \
  --image gcr.io/$PROJECT_ID/$SERVICE \
  --platform managed \
  --region $REGION \
  --allow-unauthenticated \
  --set-env-vars HENET_API_KEY=change-me,CORS_ORIGINS=https://www.teddyallen.com
```
