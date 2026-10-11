// The list of pages and their web addresses.

import { lazy, Suspense, type ReactNode } from "react";
import { createBrowserRouter, Navigate } from "react-router";

// Code-split by area: the landing page, the login screen and the app load separately.
const Landing = lazy(() => import("@/pages/Landing"));
const Login = lazy(() => import("@/pages/Login"));
const AppLayout = lazy(() => import("@/pages/app/AppLayout"));
const Ask = lazy(() => import("@/pages/app/Ask"));
const Data = lazy(() => import("@/pages/app/Data"));
const TracePage = lazy(() => import("@/pages/app/TracePage"));
const Brief = lazy(() => import("@/pages/app/Brief"));
const KitGallery = lazy(() => import("@/pages/KitGallery"));
const NotFound = lazy(() => import("@/pages/NotFound"));

const page = (node: ReactNode) => <Suspense fallback={null}>{node}</Suspense>;

export const router = createBrowserRouter([
  { path: "/", element: page(<Landing />) },
  { path: "/login", element: page(<Login />) },
  {
    path: "/app",
    element: page(<AppLayout />),
    children: [
      { index: true, element: <Navigate to="ask" replace /> },
      { path: "ask", element: page(<Ask />) },
      { path: "data", element: page(<Data />) },
      { path: "trace", element: page(<TracePage />) },
      { path: "trace/:runId", element: page(<TracePage />) },
    ],
  },
  { path: "/app/brief/:runId", element: page(<Brief />) },
  ...(import.meta.env.DEV ? [{ path: "/_kit", element: page(<KitGallery />) }] : []),
  { path: "*", element: page(<NotFound />) },
]);
