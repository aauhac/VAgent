/**
 * Minimal markdown renderer for legal pages. No raw HTML passthrough.
 */
import type { ReactNode } from 'react';

function stripMeta(md: string): string {
  return md.replace(/<!--[\s\S]*?-->/g, '').trim();
}

function isTableSep(line: string): boolean {
  return /^\s*\|?\s*:?-{3,}/.test(line);
}

function splitRow(line: string): string[] {
  const t = line.trim();
  const inner = t.startsWith('|') ? t.slice(1) : t;
  const end = inner.endsWith('|') ? inner.slice(0, -1) : inner;
  return end.split('|').map((c) => c.trim());
}

function inline(text: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /(\*\*[^*]+\*\*|`[^`]+`|\[[^\]]+\]\([^)]+\))/g;
  let last = 0;
  let m: RegExpExecArray | null;
  let i = 0;
  while ((m = re.exec(text))) {
    if (m.index > last) nodes.push(text.slice(last, m.index));
    const token = m[0];
    if (token.startsWith('**')) {
      nodes.push(<strong key={i}>{token.slice(2, -2)}</strong>);
    } else if (token.startsWith('`')) {
      nodes.push(<code key={i}>{token.slice(1, -1)}</code>);
    } else {
        const lm = token.match(/^\[([^\]]+)\]\((https?:\/\/[^)]+)\)$/);
        if (lm) {
          nodes.push(
            <a key={i} href={lm[2]} rel="noreferrer" target="_blank">
              {lm[1]}
            </a>,
          );
        }
    }
    i += 1;
    last = m.index + token.length;
  }
  if (last < text.length) nodes.push(text.slice(last));
  return nodes;
}

export default function LegalMarkdown({ source }: { source: string }) {
  const lines = stripMeta(source).split(/\r?\n/);
  const out: ReactNode[] = [];
  let i = 0;
  let key = 0;
  while (i < lines.length) {
    const line = lines[i];
    if (!line.trim()) {
      i += 1;
      continue;
    }
    if (line.startsWith('# ')) {
      out.push(<h1 key={key++}>{line.slice(2)}</h1>);
      i += 1;
      continue;
    }
    if (line.startsWith('## ')) {
      out.push(<h2 key={key++}>{line.slice(3)}</h2>);
      i += 1;
      continue;
    }
    if (line.startsWith('### ')) {
      out.push(<h3 key={key++}>{line.slice(4)}</h3>);
      i += 1;
      continue;
    }
    if (line.trim().startsWith('|')) {
      const rows: string[][] = [];
      while (i < lines.length && lines[i].trim().startsWith('|')) {
        if (!isTableSep(lines[i])) rows.push(splitRow(lines[i]));
        i += 1;
      }
      if (rows.length) {
        const head = rows[0];
        const body = rows.slice(1);
        out.push(
          <div className="legal-table-wrap" key={key++}>
            <table>
              <thead>
                <tr>
                  {head.map((c) => (
                    <th key={c}>{inline(c)}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {body.map((r, ri) => (
                  <tr key={ri}>
                    {r.map((c, ci) => (
                      <td key={ci}>{inline(c)}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>,
        );
      }
      continue;
    }
    if (line.trim().startsWith('- ')) {
      const items: string[] = [];
      while (i < lines.length && lines[i].trim().startsWith('- ')) {
        items.push(lines[i].trim().slice(2));
        i += 1;
      }
      out.push(
        <ul key={key++}>
          {items.map((it, ii) => (
            <li key={ii}>{inline(it)}</li>
          ))}
        </ul>,
      );
      continue;
    }
    if (/^\d+\.\s/.test(line.trim())) {
      const items: string[] = [];
      while (i < lines.length && /^\d+\.\s/.test(lines[i].trim())) {
        items.push(lines[i].trim().replace(/^\d+\.\s/, ''));
        i += 1;
      }
      out.push(
        <ol key={key++}>
          {items.map((it, ii) => (
            <li key={ii}>{inline(it)}</li>
          ))}
        </ol>,
      );
      continue;
    }
    const para: string[] = [line];
    i += 1;
    while (
      i < lines.length
      && lines[i].trim()
      && !lines[i].startsWith('#')
      && !lines[i].trim().startsWith('|')
      && !lines[i].trim().startsWith('- ')
      && !/^\d+\.\s/.test(lines[i].trim())
    ) {
      para.push(lines[i]);
      i += 1;
    }
    out.push(<p key={key++}>{inline(para.join(' '))}</p>);
  }
  return <article className="legal-doc">{out}</article>;
}
