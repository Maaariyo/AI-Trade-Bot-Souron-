import { Suspense } from "react";

import { ApiStatus } from "@/components/api-status";
import { Placeholder } from "@/components/placeholder";
import { screenFor } from "@/lib/routes";

export default function DashboardPage() {
  return (
    <Placeholder screen={screenFor("/")}>
      <div className="space-y-2">
        <h2 className="text-sm font-medium uppercase tracking-wide text-muted">System</h2>
        <Suspense fallback={<p className="text-sm text-muted">Checking the API…</p>}>
          <ApiStatus />
        </Suspense>
      </div>
    </Placeholder>
  );
}
