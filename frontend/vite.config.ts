// @lovable.dev/vite-tanstack-config already includes the following — do NOT add them manually
// or the app will break with duplicate plugins:
//   - TanStack devtools (dev-only, first), tanstackStart, viteReact, tailwindcss, tsConfigPaths,
//     nitro (build-only using cloudflare as a default target), VITE_* env injection, @ path alias,
//     React/TanStack dedupe, error logger plugins, and sandbox detection (port/host/strictPort).
// You can pass additional config via defineConfig({ vite: { ... }, etc... }) if needed.
import { defineConfig } from "@lovable.dev/vite-tanstack-config";

// Same-origin proxy so the PWA (and its session cookie) talks to the Python engine through one URL/tunnel.
const proxy = { "/api": { target: process.env.API_TARGET || "http://127.0.0.1:8000", changeOrigin: true } };

export default defineConfig({
  vite: {
    server: { proxy, host: true, allowedHosts: true },
    preview: { proxy, host: true, allowedHosts: true },
    optimizeDeps: {
      // Prebundle shared UI dependencies together with React before routes load.
      // Late optimization can otherwise mix stale React URLs in an open preview.
      include: ["@radix-ui/react-dialog", "@radix-ui/react-slot", "lucide-react", "leaflet"],
    },
  },
  tanstackStart: {
    // Redirect TanStack Start's bundled server entry to src/server.ts (our SSR error wrapper).
    // nitro/vite builds from this
    server: { entry: "server" },
  },
});
