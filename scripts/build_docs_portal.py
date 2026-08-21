"""Portal de documentação: os documentos canônicos reunidos num HTML único e navegável.

O problema que ele resolve não é falta de documentação — é acesso. Ler o sistema hoje
exige entrar no repositório e abrir um `.md` de cada vez. Este script renderiza os
documentos que o manifesto lista numa página só, com navegação lateral e busca, que se lê
fora do repositório.

**A fonte de verdade continua sendo o Markdown.** Esta página é derivada e descartável:
ela vai para `output/`, que é temporário e ignorado pelo Git. Editar o HTML gerado é
sempre erro; edite o documento e rode `make docs` de novo.

Quais documentos entram é decisão declarada em `docs/portal.manifest.json`, no mesmo molde
do `contracts.manifest.json`: acrescentar um documento ao portal é editar dado, não código.

Cada documento carrega um selo de frescor que compara a data que ele declara no cabeçalho
("Última revisão") com a data do último commit que tocou o arquivo. Divergência não é erro
— é informação: um documento cuja última revisão declarada é anterior ao último commit
mudou sem que alguém revisse a data, e isso aparece na página em vez de ficar escondido.
"""

from __future__ import annotations

import html
import json
import re
import subprocess
import sys
import unicodedata
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any, Final

from markdown_it import MarkdownIt

REPO_ROOT: Final = Path(__file__).resolve().parent.parent
MANIFEST_PATH: Final = REPO_ROOT / "docs" / "portal.manifest.json"
DEFAULT_OUTPUT: Final = REPO_ROOT / "output" / "docs-portal.html"

_H1: Final = re.compile(r"^#\s+(.+)$", re.MULTILINE)
_META_LINE: Final = re.compile(r"^(Status|Responsável|Última revisão):\s*(.+?)\s*$", re.MULTILINE)
_ISO_DATE: Final = re.compile(r"(\d{4}-\d{2}-\d{2})")
_HEADING: Final = re.compile(r"<h([23])>(.*?)</h\1>", re.DOTALL)
_TAG: Final = re.compile(r"<[^>]+>")


def slugify(text: str) -> str:
    """Âncora estável a partir de um título: sem acento, sem pontuação, hifenizada."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    plain = re.sub(r"[^a-zA-Z0-9]+", "-", plain).strip("-").lower()
    return plain or "secao"


def git_last_commit_date(path: Path) -> str | None:
    """Data do último commit que tocou o arquivo, ou `None` se ele nunca foi commitado.

    Documento ainda não versionado é estado legítimo (acabou de ser escrito) e aparece
    como tal na página — não é tratado como erro nem como data ausente por falha.
    """
    result = subprocess.run(
        ["git", "log", "-1", "--format=%as", "--", str(path)],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    stamp = result.stdout.strip()
    return stamp if result.returncode == 0 and _ISO_DATE.fullmatch(stamp) else None


@dataclass(frozen=True, slots=True)
class Freshness:
    """Comparação entre a data declarada no cabeçalho e a do último commit."""

    declared: str | None
    committed: str | None

    @property
    def state(self) -> str:
        if self.committed is None:
            return "novo"
        if self.declared is None:
            return "sem-data"
        return "defasado" if self.declared < self.committed else "em-dia"

    @property
    def label(self) -> str:
        return {
            "novo": "ainda não versionado",
            "sem-data": "sem data declarada",
            "defasado": f"revisão declarada {self.declared} · commit {self.committed}",
            "em-dia": f"revisão {self.declared or self.committed}",
        }[self.state]


@dataclass(frozen=True, slots=True)
class Document:
    slug: str
    title: str
    status: str | None
    owner: str | None
    freshness: Freshness
    body_html: str
    source: str
    subheadings: tuple[tuple[str, str], ...]


def read_document(
    relative_path: str, renderer: MarkdownIt, portal_targets: dict[str, str]
) -> Document:
    """Lê um documento do manifesto e devolve tudo que a página precisa dele."""
    path = REPO_ROOT / relative_path
    if not path.is_file():
        raise SystemExit(f"portal: documento do manifesto não existe -> {relative_path}")
    text = path.read_text(encoding="utf-8")

    title_match = _H1.search(text)
    if title_match is None:
        raise SystemExit(f"portal: {relative_path} não tem título de nível 1")
    title = title_match.group(1).strip()
    slug = slugify(relative_path.rsplit("/", 1)[-1].removesuffix(".md"))

    meta = {key: value for key, value in _META_LINE.findall(text)}
    declared = None
    if "Última revisão" in meta:
        found = _ISO_DATE.search(meta["Última revisão"])
        declared = found.group(1) if found else None

    # O H1 e o bloco de metadados viram cabeçalho da seção na página; renderizar de novo
    # no corpo duplicaria os dois.
    body_source = _H1.sub("", text, count=1)
    body_source = _META_LINE.sub("", body_source)

    body_html = renderer.render(body_source)
    body_html = _rewrite_links(body_html, relative_path, portal_targets)
    body_html, subheadings = _anchor_headings(body_html, slug)

    return Document(
        slug=slug,
        title=title,
        status=meta.get("Status"),
        owner=meta.get("Responsável"),
        freshness=Freshness(declared=declared, committed=git_last_commit_date(path)),
        body_html=body_html,
        source=relative_path,
        subheadings=subheadings,
    )


def _rewrite_links(body: str, source: str, portal_targets: dict[str, str]) -> str:
    """Liga o que está no portal e desarma o que não está.

    Um link relativo para um documento que o portal também renderiza vira âncora interna.
    Um link para arquivo do repositório que o portal NÃO tem deixa de ser link: vira texto
    com o caminho, porque link para o sistema de arquivos não abre nada fora do repo e um
    link morto é pior que uma referência honesta.
    """
    source_dir = Path(source).parent

    def replace(match: re.Match[str]) -> str:
        target = match.group(1)
        if target.startswith(("http://", "https://", "mailto:", "#")):
            return match.group(0)
        anchor = ""
        if "#" in target:
            target, anchor = target.split("#", 1)
        resolved = str((source_dir / target).resolve().relative_to(REPO_ROOT)) if target else ""
        if resolved in portal_targets:
            return f'href="#{portal_targets[resolved]}"'
        # Fora do portal: o texto do link continua legível e o caminho vai para o `title`,
        # em vez de ser concatenado ao texto ou virar um href que não abre nada.
        return f'class="ref" title="{html.escape(resolved or anchor)}"'

    return re.sub(r'href="([^"]+)"', replace, body)


def _anchor_headings(body: str, slug: str) -> tuple[str, tuple[tuple[str, str], ...]]:
    """Dá âncora a cada h2/h3 e devolve os h2 para a navegação lateral."""
    subheadings: list[tuple[str, str]] = []

    def replace(match: re.Match[str]) -> str:
        level, inner = match.group(1), match.group(2)
        plain = html.unescape(_TAG.sub("", inner)).strip()
        anchor = f"{slug}--{slugify(plain)}"
        if level == "2":
            subheadings.append((anchor, plain))
        return f'<h{level} id="{anchor}">{inner}</h{level}>'

    return _HEADING.sub(replace, body), tuple(subheadings)


def build(manifest: dict[str, Any]) -> str:
    renderer = MarkdownIt("commonmark", {"html": True, "linkify": False}).enable("table")

    portal_targets = {
        doc: slugify(doc.rsplit("/", 1)[-1].removesuffix(".md"))
        for section in manifest["sections"]
        for doc in section["docs"]
    }

    sections: list[tuple[dict[str, Any], list[Document]]] = [
        (section, [read_document(doc, renderer, portal_targets) for doc in section["docs"]])
        for section in manifest["sections"]
    ]
    return render_page(manifest, sections)


def render_page(
    manifest: dict[str, Any], sections: list[tuple[dict[str, Any], list[Document]]]
) -> str:
    nav: list[str] = []
    main: list[str] = []

    for section, documents in sections:
        section_slug = slugify(section["label"])
        nav.append(f'<li class="nav-section"><span>{html.escape(section["label"])}</span><ul>')
        for document in documents:
            nav.append(
                f'<li class="nav-doc" data-search="{html.escape(document.title.lower())}">'
                f'<a href="#{document.slug}">{html.escape(document.title)}</a>'
            )
            if document.subheadings:
                nav.append('<ul class="nav-sub">')
                for anchor, text in document.subheadings:
                    nav.append(
                        f'<li data-search="{html.escape(text.lower())}">'
                        f'<a href="#{anchor}">{html.escape(text)}</a></li>'
                    )
                nav.append("</ul>")
            nav.append("</li>")
        nav.append("</ul></li>")

        main.append(f'<section class="doc-section" id="{section_slug}">')
        main.append(
            f'<p class="section-blurb">{html.escape(section.get("blurb", ""))}</p>'
            if section.get("blurb")
            else ""
        )
        for document in documents:
            main.append(render_document(document))
        main.append("</section>")

    generated = date.today().isoformat()
    return _SHELL.format(
        title=html.escape(manifest["title"]),
        subtitle=html.escape(manifest.get("subtitle", "")),
        nav="\n".join(nav),
        main="\n".join(main),
        generated=generated,
        css=_CSS,
        js=_JS,
    )


def render_document(document: Document) -> str:
    chips = [
        f'<span class="chip chip-{document.freshness.state}">'
        f"{html.escape(document.freshness.label)}</span>"
    ]
    if document.status:
        chips.insert(0, f'<span class="chip">{html.escape(document.status)}</span>')
    if document.owner:
        chips.append(f'<span class="chip chip-quiet">{html.escape(document.owner)}</span>')
    return (
        f'<article class="doc" id="{document.slug}" '
        f'data-search="{html.escape(document.title.lower())}">'
        f'<header class="doc-head">'
        f"<h1>{html.escape(document.title)}</h1>"
        f'<div class="chips">{"".join(chips)}</div>'
        f'<p class="src">{html.escape(document.source)}</p>'
        f"</header>{document.body_html}</article>"
    )


_CSS = """
:root{--paper:#F6F7F5;--surface:#FFFFFF;--ink:#15181D;--muted:#5B626D;--faint:#858C97;
--rule:#DBDDE0;--rule-soft:#E9EAEC;--accent:#2F4B7C;--accent-bg:#EDF1F8;--warn:#7C6414;
--warn-bg:#F7F2DF;--ok:#3B6B4A;--up:#96442A;
--mono:ui-monospace,"SF Mono",SFMono-Regular,Menlo,Consolas,monospace;
--serif:ui-serif,"Iowan Old Style","Palatino Linotype",Palatino,Georgia,serif}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--paper:#111419;
--surface:#171B21;--ink:#E6E8EB;--muted:#9BA3AE;--faint:#78808B;--rule:#2B3038;
--rule-soft:#22262D;--accent:#8FADDE;--accent-bg:#1A2231;--warn:#CFB25A;--warn-bg:#262114;
--ok:#7FB18E;--up:#DE9573}}
:root[data-theme="dark"]{--paper:#111419;--surface:#171B21;--ink:#E6E8EB;--muted:#9BA3AE;
--faint:#78808B;--rule:#2B3038;--rule-soft:#22262D;--accent:#8FADDE;--accent-bg:#1A2231;
--warn:#CFB25A;--warn-bg:#262114;--ok:#7FB18E;--up:#DE9573}
body{background:var(--paper);color:var(--ink);font-family:var(--serif);font-size:17px;
line-height:1.62;-webkit-font-smoothing:antialiased}
.layout{display:grid;grid-template-columns:minmax(15rem,19rem) minmax(0,1fr);
align-items:start;gap:0;max-width:96rem;margin:0 auto}
@media (max-width:900px){.layout{grid-template-columns:1fr}
aside{position:static !important;height:auto !important;border-right:0 !important;
border-bottom:1px solid var(--rule)}}
aside{position:sticky;top:0;height:100vh;overflow-y:auto;padding:1.6rem 1.2rem 3rem;
border-right:1px solid var(--rule);display:flex;flex-direction:column;gap:1rem}
.brand{font-family:var(--mono);font-size:.7rem;letter-spacing:.16em;text-transform:uppercase;
color:var(--faint)}
.search{width:100%;padding:.5rem .65rem;font:inherit;font-size:.85rem;color:var(--ink);
background:var(--surface);border:1px solid var(--rule);border-radius:3px}
.search:focus-visible{outline:2px solid var(--accent);outline-offset:1px}
nav ul{list-style:none;margin:0;padding:0}
.nav-section>span{display:block;font-family:var(--mono);font-size:.63rem;letter-spacing:.13em;
text-transform:uppercase;color:var(--faint);margin:1.1rem 0 .45rem;padding-bottom:.3rem;
border-bottom:1px solid var(--rule-soft)}
nav a{color:var(--ink);text-decoration:none;display:block;padding:.2rem 0;font-size:.92rem}
nav a:hover{color:var(--accent)}
nav a:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
.nav-sub{margin:.15rem 0 .5rem .1rem;padding-left:.7rem;border-left:1px solid var(--rule-soft)}
.nav-sub a{font-size:.82rem;color:var(--muted);padding:.12rem 0}
li.hidden{display:none}
main{padding:clamp(1.8rem,4vw,3.5rem) clamp(1.1rem,4vw,3rem) 8rem;min-width:0}
.masthead{max-width:74ch;display:flex;flex-direction:column;gap:.7rem;
padding-bottom:1.4rem;border-bottom:2px solid var(--ink);margin-bottom:1rem}
.masthead h1{font-size:clamp(1.7rem,3.6vw,2.4rem);line-height:1.15;font-weight:600;
letter-spacing:-.015em;margin:0;text-wrap:balance}
.masthead p{color:var(--muted);margin:0;font-size:1.02rem}
.section-blurb{color:var(--muted);font-size:.98rem;max-width:66ch;margin:0 0 .5rem}
.doc-section{display:flex;flex-direction:column;gap:1rem;margin-top:2.6rem}
.doc{max-width:76ch;display:flex;flex-direction:column;gap:.9rem;scroll-margin-top:1.5rem}
.doc.hidden{display:none}
.doc-head{display:flex;flex-direction:column;gap:.5rem;padding-bottom:.9rem;
border-bottom:1px solid var(--rule)}
.doc-head h1{font-size:clamp(1.35rem,2.6vw,1.8rem);line-height:1.2;margin:0;font-weight:600;
letter-spacing:-.01em;text-wrap:balance}
.chips{display:flex;flex-wrap:wrap;gap:.4rem}
.chip{font-family:var(--mono);font-size:.6rem;letter-spacing:.08em;text-transform:uppercase;
padding:.22em .5em;border:1px solid var(--rule);border-radius:2px;color:var(--muted)}
.chip-quiet{color:var(--faint)}
.chip-em-dia{color:var(--ok);border-color:currentColor}
.chip-defasado{color:var(--warn);background:var(--warn-bg);border-color:currentColor}
.chip-novo,.chip-sem-data{color:var(--faint);border-style:dashed}
.src{font-family:var(--mono);font-size:.68rem;color:var(--faint);margin:0}
.doc h2{font-family:var(--mono);font-size:.74rem;letter-spacing:.15em;text-transform:uppercase;
font-weight:600;margin:1.9rem 0 0;padding-bottom:.45rem;border-bottom:1px solid var(--rule);
scroll-margin-top:1.5rem}
.doc h3{font-family:var(--mono);font-size:.7rem;letter-spacing:.11em;text-transform:uppercase;
color:var(--muted);font-weight:600;margin:1.1rem 0 -.4rem;scroll-margin-top:1.5rem}
.doc p{margin:.85rem 0;max-width:68ch}
.doc ul,.doc ol{margin:.7rem 0;padding-left:1.3rem;max-width:68ch;
display:flex;flex-direction:column;gap:.3rem}
.doc li>ul,.doc li>ol{margin:.3rem 0}
.doc a{color:var(--accent);text-underline-offset:2px}
.doc a.ref{color:var(--muted);text-decoration:none;cursor:default;
font-family:var(--mono);font-size:.82em;border-bottom:1px dotted var(--rule)}
.doc code{font-family:var(--mono);font-size:.84em;background:var(--rule-soft);
padding:.1em .38em;border-radius:2px;word-break:break-word}
.doc pre{background:var(--surface);border:1px solid var(--rule);padding:.9rem 1rem;
overflow-x:auto;font-size:.82rem;line-height:1.55}
.doc pre code{background:none;padding:0;font-size:1em}
.doc blockquote{margin:1rem 0;padding:.1rem 0 .1rem 1.05rem;border-left:3px solid var(--accent);
color:var(--muted)}
.doc blockquote p{max-width:64ch}
.doc table{border-collapse:collapse;width:100%;font-size:.87rem}
.doc thead th{font-family:var(--mono);font-size:.63rem;letter-spacing:.11em;
text-transform:uppercase;color:var(--faint);font-weight:600;text-align:left;
border-bottom:1px solid var(--rule);padding:.55rem .75rem;white-space:nowrap}
.doc td,.doc tbody th{padding:.55rem .75rem;border-bottom:1px solid var(--rule-soft);
vertical-align:top;text-align:left}
.doc table{display:block;overflow-x:auto}
.doc svg{display:block;max-width:100%;height:auto;margin:0 auto}
/* Os diagramas vivem como SVG inline dentro do proprio Markdown e tomam cor destes
   tokens, nunca de hex literal: e o que faz o mesmo desenho servir aos dois temas. */
.figbox{overflow-x:auto;border:1px solid var(--rule);background:var(--surface);
padding:1.1rem .8rem}
.doc svg text{font-family:var(--serif);fill:var(--ink)}
.doc svg text.mono{font-family:var(--mono);font-weight:600}
.doc svg .t-down{fill:var(--accent)}.doc svg .t-up{fill:var(--up)}
.doc svg .t-gap{fill:var(--warn)}.doc svg .quiet{fill:var(--muted)}
.doc svg .l-ink{stroke:var(--ink)}.doc svg .l-down{stroke:var(--accent)}
.doc svg .l-up{stroke:var(--up)}.doc svg .l-gap{stroke:var(--warn)}
.doc svg .f-ink{fill:var(--ink)}.doc svg .f-down{fill:var(--accent)}
.doc svg .f-up{fill:var(--up)}.doc svg .f-gap{fill:var(--warn)}
.doc figure{margin:1.1rem 0;display:flex;flex-direction:column;gap:.6rem}
.doc figcaption{font-size:.85rem;color:var(--muted);max-width:62ch}
.doc hr{border:0;border-top:1px solid var(--rule);margin:1.6rem 0}
.empty{color:var(--muted);font-family:var(--mono);font-size:.8rem;display:none}
.empty.on{display:block}
footer{margin-top:3rem;padding-top:1rem;border-top:1px solid var(--rule);
font-family:var(--mono);font-size:.67rem;letter-spacing:.05em;color:var(--faint);
line-height:1.7;max-width:76ch}
@media (prefers-reduced-motion:reduce){*{scroll-behavior:auto !important}}
html{scroll-behavior:smooth}
"""

_JS = """
(function(){
  var box = document.getElementById('q');
  var docs = Array.prototype.slice.call(document.querySelectorAll('.doc'));
  var navItems = Array.prototype.slice.call(document.querySelectorAll('nav li[data-search]'));
  var empty = document.getElementById('empty');
  if (!box) { return; }
  function norm(s){ return s.normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase(); }
  box.addEventListener('input', function(){
    var q = norm(box.value.trim());
    var hits = 0;
    docs.forEach(function(d){
      var match = q === '' || norm(d.textContent).indexOf(q) !== -1;
      d.classList.toggle('hidden', !match);
      if (match) { hits++; }
    });
    navItems.forEach(function(li){
      var hay = norm(li.getAttribute('data-search'));
      li.classList.toggle('hidden', q !== '' && hay.indexOf(q) === -1);
    });
    empty.classList.toggle('on', hits === 0);
  });
})();
"""

_SHELL = """<title>{title}</title>
<style>{css}</style>
<div class="layout">
  <aside>
    <span class="brand">Croquito · documentação</span>
    <input id="q" class="search" type="search" placeholder="Buscar no conteúdo…"
           aria-label="Buscar na documentação">
    <nav><ul>
{nav}
    </ul></nav>
  </aside>
  <main>
    <header class="masthead">
      <h1>{title}</h1>
      <p>{subtitle}</p>
    </header>
    <p id="empty" class="empty">Nenhum documento contém esse termo.</p>
{main}
    <footer>
      Gerado por <code>make docs</code> em {generated} · a fonte de verdade é o Markdown
      versionado em <code>docs/</code>; esta página é derivada e não deve ser editada à mão.
      Quais documentos entram é declarado em <code>docs/portal.manifest.json</code>.
    </footer>
  </main>
</div>
<script>{js}</script>
"""


def main(argv: list[str]) -> int:
    output = Path(argv[1]) if len(argv) > 1 else DEFAULT_OUTPUT
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    page = build(manifest)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(page, encoding="utf-8")
    size_kb = len(page.encode("utf-8")) / 1024
    print(f"Portal gerado: {output} ({size_kb:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
