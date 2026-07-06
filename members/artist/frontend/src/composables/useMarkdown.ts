export function renderMarkdown(text: string): string {
  const codeBlocks: string[] = []

  let html = text
    .replace(/```(\w*)\n?([\s\S]*?)```/g, (_, _lang, code) => {
      const escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      codeBlocks.push(`<pre><code>${escaped.trim()}</code></pre>`)
      return `\x00CB${codeBlocks.length - 1}\x00`
    })
    .replace(/`([^`]+)`/g, (_, code) => {
      const escaped = code.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')
      codeBlocks.push(`<code>${escaped}</code>`)
      return `\x00CB${codeBlocks.length - 1}\x00`
    })
    .replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;')

  html = html.replace(/\*\*\*(.+?)\*\*\*/g, '<strong><em>$1</em></strong>')
  html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>')
  html = html.replace(/\*(.+?)\*/g, '<em>$1</em>')

  html = html.replace(/^### (.+)$/gm, '<h3>$1</h3>')
  html = html.replace(/^## (.+)$/gm, '<h2>$1</h2>')
  html = html.replace(/^# (.+)$/gm, '<h1>$1</h1>')

  html = html.replace(/^>\s?(.+)$/gm, '<blockquote>$1</blockquote>')

  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, (_, text, href) => {
    if (/^(javascript|data|vbscript):/i.test(href)) return text
    return `<a href="${href}" target="_blank" rel="noopener noreferrer">${text}</a>`
  })

  html = html.replace(/^(\d+)\.\s(.+)$/gm, '<li value="$1">$2</li>')
  html = html.replace(/^[-*]\s(.+)$/gm, '<li>$1</li>')

  html = html.replace(/(<li[^>]*>[\s\S]*?<\/li>\n?)+/g, (match) => {
    return `<${/value=/.test(match) ? 'ol' : 'ul'}>${match}</${/value=/.test(match) ? 'ol' : 'ul'}>`
  })

  html = html.replace(/---+/g, '<hr>')
  html = html.replace(/\n\s*\n/g, '\n')
  html = html.replace(/\n/g, '<br>')

  if (!/^<(?:h[1-3]|pre|ul|ol|blockquote|hr)/.test(html.trim())) {
    html = `<p>${html}</p>`
  }

  html = html.replace(/\x00CB(\d+)\x00/g, (_, i) => codeBlocks[parseInt(i)])

  return html
}
