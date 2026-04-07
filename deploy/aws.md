# Deploy to AWS App Runner

1. Push this repo to GitHub.
2. In AWS App Runner, create a new service from source.
3. Runtime: Docker.
4. Port: 8000.
5. Add environment variables:
   - `HENET_API_KEY`
   - `CORS_ORIGINS=https://www.teddyallen.com`
6. Health check path: `/health`.
