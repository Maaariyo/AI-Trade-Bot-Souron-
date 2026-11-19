import Link from "next/link";

import { SCREENS } from "@/lib/routes";

export function Nav() {
  return (
    <nav aria-label="Main" className="border-b border-line">
      <div className="mx-auto flex max-w-6xl items-center gap-6 overflow-x-auto px-4 py-3">
        <Link href="/" className="shrink-0 font-semibold tracking-tight">
          NiveshCouncil
        </Link>
        <ul className="flex gap-4 text-sm text-muted">
          {SCREENS.map((s) => (
            <li key={s.href} className="shrink-0">
              <Link href={s.href} className="hover:text-fg">
                {s.label}
              </Link>
            </li>
          ))}
        </ul>
      </div>
    </nav>
  );
}
