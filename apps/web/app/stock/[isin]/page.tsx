import { Suspense } from "react";

import { Placeholder } from "@/components/placeholder";
import { isValidIsin } from "@/lib/isin";
import { STOCK_SCREEN } from "@/lib/routes";

async function IsinLine({ params }: { params: PageProps<"/stock/[isin]">["params"] }) {
  const { isin } = await params;
  const value = decodeURIComponent(isin).toUpperCase();
  return isValidIsin(value) ? (
    <p className="font-mono text-sm">ISIN {value}</p>
  ) : (
    <p className="text-sm text-down">▼ {value} is not a valid ISIN.</p>
  );
}

export default function StockCouncilPage(props: PageProps<"/stock/[isin]">) {
  return (
    <Placeholder screen={STOCK_SCREEN}>
      <Suspense fallback={<p className="text-sm text-muted">Reading the ISIN…</p>}>
        <IsinLine params={props.params} />
      </Suspense>
    </Placeholder>
  );
}
