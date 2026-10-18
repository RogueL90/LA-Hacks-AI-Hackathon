import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  // The built viewer is also served through a public tunnel (e.g. *.trycloudflare.com).
  preview: { allowedHosts: true },
});
