export type ComposerSyntaxKind = 'resource' | 'slash';

export interface ComposerSyntaxSpan {
  kind: ComposerSyntaxKind;
  start: number;
  end: number;
  raw: string;
  value: string;
  quoted: boolean;
}

const RESOURCE_STOP = new Set('，。；：！？、,!?;)]}）】》”'.split(''));
const COMMAND_NAME = /^[A-Za-z0-9_-]$/;
const QUOTES = new Set(['"', "'", '“', '”', '‘', '’']);

export function parseComposerSyntax(text: string): ComposerSyntaxSpan[] {
  const spans: ComposerSyntaxSpan[] = [];
  let inlineCode = false;
  let quote: string | null = null;
  let fence = false;
  let lineStart = true;

  for (let i = 0; i < text.length; i += 1) {
    const ch = text[i];
    const next3 = text.slice(i, i + 3);

    if (lineStart && next3 === '```') {
      fence = !fence;
      i += 2;
      lineStart = false;
      continue;
    }

    if (ch === '\n') {
      lineStart = true;
      continue;
    }
    if (lineStart && ch !== '\r') lineStart = false;
    if (fence) continue;

    if (ch === '`') {
      inlineCode = !inlineCode;
      continue;
    }
    if (inlineCode) continue;

    if (quote) {
      if (matchesQuoteClose(quote, ch)) quote = null;
      continue;
    }
    if (QUOTES.has(ch)) {
      quote = ch;
      continue;
    }

    if ((ch === '@' || ch === '/') && isSyntaxBoundary(text, i)) {
      const span = ch === '@' ? parseResource(text, i) : parseSlash(text, i);
      if (span) {
        spans.push(span);
        i = span.end - 1;
      }
    }
  }

  return spans;
}

export function findActiveSlashCandidate(text: string, cursor: number): ComposerSyntaxSpan | null {
  return (
    parseComposerSyntax(text).find(
      (span) => span.kind === 'slash' && span.start < cursor && cursor <= span.end,
    ) ?? null
  );
}

function isSyntaxBoundary(text: string, index: number): boolean {
  return index === 0 || /\s/.test(text[index - 1] ?? '');
}

function matchesQuoteClose(open: string, close: string): boolean {
  if (open === '“') return close === '”';
  if (open === '‘') return close === '’';
  return open === close;
}

function parseResource(text: string, start: number): ComposerSyntaxSpan | null {
  const first = text[start + 1];
  if (!first) return null;
  if (first === '"' || first === "'") {
    const close = text.indexOf(first, start + 2);
    if (close === -1) return null;
    const raw = text.slice(start, close + 1);
    return {
      kind: 'resource',
      start,
      end: close + 1,
      raw,
      value: text.slice(start + 2, close),
      quoted: true,
    };
  }
  let end = start + 1;
  while (end < text.length) {
    const ch = text[end];
    if (/\s/.test(ch) || RESOURCE_STOP.has(ch)) {
      if (!(ch === ':' && end === start + 2 && /[A-Za-z]/.test(first))) {
        break;
      }
    }
    end += 1;
  }
  if (end === start + 1) return null;
  const raw = text.slice(start, end);
  return {
    kind: 'resource',
    start,
    end,
    raw,
    value: raw.slice(1),
    quoted: false,
  };
}

function parseSlash(text: string, start: number): ComposerSyntaxSpan | null {
  let end = start + 1;
  while (end < text.length && COMMAND_NAME.test(text[end])) end += 1;
  const raw = text.slice(start, end);
  return {
    kind: 'slash',
    start,
    end,
    raw,
    value: raw.slice(1),
    quoted: false,
  };
}
