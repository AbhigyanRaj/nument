// App entry point: loads styles and starts React with routing and data fetching.

import "@fontsource-variable/figtree";
import "@fontsource-variable/newsreader/opsz.css";
import "@fontsource/dm-mono/400.css";
import "@fontsource/dm-mono/500.css";
import "./index.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { RouterProvider } from "react-router";
import { Toaster } from "sonner";

import { TooltipProvider } from "@/components/ui/controls";
import { router } from "@/router";

// Full-page captures (?capture) show every reveal immediately.
if (new URLSearchParams(window.location.search).has("capture")) {
  document.documentElement.classList.add("capture");
}

const queryClient = new QueryClient({
  defaultOptions: { queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 15_000 } },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <TooltipProvider>
        <RouterProvider router={router} />
        <Toaster
          position="bottom-center"
          toastOptions={{
            className:
              "!rounded-2xl !border !border-st-secondary !bg-white !font-sans !text-caption !text-tx !shadow-[0_12px_40px_-8px_#0000001f]",
          }}
        />
      </TooltipProvider>
    </QueryClientProvider>
  </StrictMode>,
);
