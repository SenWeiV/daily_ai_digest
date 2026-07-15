import { ExternalLink, FileText } from "lucide-react";
import type { ArxivDigestItem } from "../types";

interface ArxivListProps {
  items: ArxivDigestItem[];
}

function ArxivList({ items }: ArxivListProps) {
  if (items.length === 0) {
    return (
      <div className="surface rounded-lg p-10 text-center text-neutral-400">
        当前摘要没有符合质量要求的 arXiv 论文
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {items.map((item) => (
        <article key={item.arxiv_id} className="surface rounded-lg p-6">
          <div className="flex items-start gap-4">
            <FileText className="mt-1 h-5 w-5 shrink-0 text-violet-400" />
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <h2 className="text-lg font-semibold leading-7 text-neutral-100">
                  {item.title}
                </h2>
                <span className="rounded border border-neutral-700 px-2 py-1 text-xs text-neutral-300">
                  {item.quality_grade} 级
                </span>
              </div>
              <p className="mt-2 text-sm text-neutral-400">
                {item.authors.slice(0, 6).join(", ")}
              </p>
              <p className="mt-4 whitespace-pre-line text-sm leading-6 text-neutral-300">
                {item.summary || item.abstract}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {item.categories.map((category) => (
                  <span key={category} className="rounded bg-neutral-800 px-2 py-1 text-xs text-neutral-400">
                    {category}
                  </span>
                ))}
              </div>
              <a
                href={item.arxiv_url}
                target="_blank"
                rel="noreferrer"
                className="mt-5 inline-flex items-center gap-2 text-sm text-violet-300 hover:text-violet-200"
              >
                查看论文 <ExternalLink className="h-4 w-4" />
              </a>
            </div>
          </div>
        </article>
      ))}
    </div>
  );
}

export default ArxivList;
