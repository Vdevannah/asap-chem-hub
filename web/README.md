# ASAP Chem Hub — website

React + Vite front end for the two tabs: ASAP Articles and New Patents.

```bash
cd web
npm install          # first time only
npm run dev          # http://localhost:5173
```

The FastAPI backend must be running (`uvicorn api.main:app --reload` from the project root).
To use a different API address, copy `.env.example` to `.env.local` and edit `VITE_API_URL`.

`npm run build` writes the static site to `dist/` (this is what goes to S3 + CloudFront later).
