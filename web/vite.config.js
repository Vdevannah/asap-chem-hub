import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The API address comes from VITE_API_URL (see .env.example); default = local FastAPI.
export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
});
