// The page shown when a link does not exist.

import { Link } from "react-router";

import { Ornament } from "@/components/brand/marks";
import { Button } from "@/components/ui/button";

export default function NotFound() {
  return (
    <div className="grid min-h-dvh place-items-center bg-sf px-6 text-center">
      <div className="flex flex-col items-center gap-4">
        <Ornament className="text-indigo-300" />
        <p className="text-xl font-medium">This page does not exist</p>
        <p className="text-body text-tx-tertiary">The link may be old, or the run was removed.</p>
        <Button asChild variant="soft">
          <Link to="/">Back to nument</Link>
        </Button>
      </div>
    </div>
  );
}
