"use client";

import { Alert, Button } from "@/components/ui";

export default function Error({ error, reset }: { error: Error; reset: () => void }) {
  return (
    <div className="mx-auto max-w-lg space-y-3 py-10">
      <Alert>{error.message || "Something went wrong."}</Alert>
      <Button variant="secondary" onClick={reset}>Try again</Button>
    </div>
  );
}
