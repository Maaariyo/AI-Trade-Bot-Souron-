"use client";

import {
  columnFilteringFeature,
  createColumnHelper,
  createFilteredRowModel,
  createPaginatedRowModel,
  createSortedRowModel,
  filterFn_includesString,
  globalFilteringFeature,
  rowPaginationFeature,
  rowSortingFeature,
  sortFn_alphanumeric,
  sortFn_basic,
  tableFeatures,
  useTable,
} from "@tanstack/react-table";
import { useMemo, useState } from "react";

import { FAMILY_LABEL, type ScoreRow, type ScoresOut } from "@/lib/scores";

const features = tableFeatures({
  columnFilteringFeature,
  globalFilteringFeature,
  rowSortingFeature,
  rowPaginationFeature,
  filteredRowModel: createFilteredRowModel(),
  sortedRowModel: createSortedRowModel(),
  paginatedRowModel: createPaginatedRowModel(),
  filterFns: { includesString: filterFn_includesString },
  sortFns: { alphanumeric: sortFn_alphanumeric, basic: sortFn_basic },
});

const helper = createColumnHelper<typeof features, ScoreRow>();
const FAMILIES = Object.keys(FAMILY_LABEL);

// Colour is never the only signal (SPEC UI rules): strong and weak cells also get an arrow.
function heat(v: number | undefined): { cls: string; mark: string } {
  if (v === undefined) return { cls: "text-muted", mark: "" };
  if (v >= 70) return { cls: "text-up", mark: "▲ " };
  if (v < 30) return { cls: "text-down", mark: "▼ " };
  return { cls: "", mark: "" };
}

const columns = helper.columns([
  helper.accessor((r) => r.rank ?? Number.MAX_SAFE_INTEGER, {
    id: "rank",
    header: "Rank",
    sortFn: sortFn_basic,
    cell: (info) => info.row.original.rank ?? "—",
  }),
  helper.accessor((r) => `${r.nse_symbol ?? r.isin} ${r.name}`, {
    id: "stock",
    header: "Stock",
    sortFn: sortFn_alphanumeric,
    cell: (info) => (
      <div>
        <div className="font-medium">
          {info.row.original.nse_symbol ?? info.row.original.isin}
        </div>
        <div className="text-xs text-muted">{info.row.original.name}</div>
      </div>
    ),
  }),
  helper.accessor((r) => r.industry ?? "", {
    id: "industry",
    header: "Industry",
    sortFn: sortFn_alphanumeric,
  }),
  helper.accessor((r) => r.composite ?? -1, {
    id: "composite",
    header: "Score",
    sortFn: sortFn_basic,
    cell: (info) => {
      const r = info.row.original;
      if (r.composite === null) return <span className="text-muted">—</span>;
      return (
        <span className={r.thin_data ? "text-muted" : "font-medium"}>
          {r.composite.toFixed(1)}
          {r.thin_data ? " (thin data)" : ""}
        </span>
      );
    },
  }),
  ...FAMILIES.map((fam) =>
    helper.accessor((r) => r.family_scores[fam] ?? -1, {
      id: fam,
      header: FAMILY_LABEL[fam],
      sortFn: sortFn_basic,
      cell: (info) => {
        const v = info.row.original.family_scores[fam];
        const h = heat(v);
        return (
          <span className={h.cls}>
            {v === undefined ? "—" : `${h.mark}${v.toFixed(0)}`}
          </span>
        );
      },
    }),
  ),
  helper.accessor((r) => (r.passed ? "pass" : r.reasons.join("; ")), {
    id: "gates",
    header: "Gates",
    sortFn: sortFn_alphanumeric,
    cell: (info) => {
      const r = info.row.original;
      return r.passed ? (
        <span className="text-up">▲ pass</span>
      ) : (
        <span className="text-down" title={r.reasons.join("; ")}>
          ▼ {r.reasons[0]}
        </span>
      );
    },
  }),
]);

export function ScreenerTable({ data }: { data: ScoresOut }) {
  const [passedOnly, setPassedOnly] = useState(true);
  const rows = useMemo(
    () => (passedOnly ? data.rows.filter((r) => r.passed) : data.rows),
    [data.rows, passedOnly],
  );
  const table = useTable({
    features,
    columns,
    data: rows,
    globalFilterFn: "includesString",
    initialState: { pagination: { pageIndex: 0, pageSize: 50 } },
  });
  const ranked = data.rows.filter((r) => r.rank !== null).length;
  const passed = data.rows.filter((r) => r.passed).length;

  return (
    <div className="space-y-3">
      <p className="text-sm text-muted">
        Screen run {data.run_id}, as of {data.as_of}: {data.rows.length}{" "}
        securities, {passed} pass the gates, {ranked} ranked.
      </p>
      {data.unavailable_factors.length > 0 && (
        <p className="text-xs text-down">
          ▼ No data yet for: {data.unavailable_factors.join(", ")}. These are
          left out of every score.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-3 text-sm">
        <input
          aria-label="Search stocks"
          placeholder="Search symbol, name or industry"
          className="min-w-0 flex-1 rounded border border-line bg-transparent px-2 py-1"
          onChange={(e) => table.setGlobalFilter(e.target.value)}
        />
        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={passedOnly}
            onChange={(e) => setPassedOnly(e.target.checked)}
          />
          Passed gates only
        </label>
        <button
          disabled
          title="The council arrives in Phase 3"
          className="rounded border border-line px-3 py-1 text-muted"
        >
          Send to council
        </button>
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            {table.getHeaderGroups().map((group) => (
              <tr
                key={group.id}
                className="border-b border-line text-left text-muted"
              >
                {group.headers.map((header) => (
                  <th
                    key={header.id}
                    className="whitespace-nowrap px-2 py-2 font-normal"
                  >
                    <button
                      type="button"
                      className="hover:text-fg"
                      onClick={header.column.getToggleSortingHandler()}
                    >
                      <table.FlexRender header={header} />
                      {{ asc: " ▲", desc: " ▼" }[
                        header.column.getIsSorted() as string
                      ] ?? ""}
                    </button>
                  </th>
                ))}
              </tr>
            ))}
          </thead>
          <tbody>
            {table.getRowModel().rows.map((row) => (
              <tr key={row.id} className="border-b border-line/50">
                {row.getAllCells().map((cell) => (
                  <td key={cell.id} className="whitespace-nowrap px-2 py-1.5">
                    <table.FlexRender cell={cell} />
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="flex items-center gap-3 text-sm">
        <button
          className="rounded border border-line px-2 py-1 disabled:opacity-40"
          onClick={() => table.previousPage()}
          disabled={!table.getCanPreviousPage()}
        >
          Previous
        </button>
        <span className="text-muted">
          Page {table.state.pagination.pageIndex + 1} of{" "}
          {Math.max(table.getPageCount(), 1)}
        </span>
        <button
          className="rounded border border-line px-2 py-1 disabled:opacity-40"
          onClick={() => table.nextPage()}
          disabled={!table.getCanNextPage()}
        >
          Next
        </button>
      </div>
    </div>
  );
}
