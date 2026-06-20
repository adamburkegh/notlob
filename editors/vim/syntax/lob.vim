" Vim syntax file for notlob literate programming (.lob)

if exists("b:current_syntax")
  finish
endif

" ── Embedded language ────────────────────────────────────────
" Default to Python; override with  let g:lob_embedded_language = 'haskell'
let s:lang = get(g:, 'lob_embedded_language', 'python')
execute 'syntax include @lobEmbedded syntax/' . s:lang . '.vim'
unlet b:current_syntax

" ── Code blocks ──────────────────────────────────────────────
" Indented lines (possibly spanning blank lines) get embedded
" language highlighting.  Region ends at the next non-blank
" line that starts in column 0.
syn region lobCodeBlock start="^\s" end="^\ze\S" contains=@lobEmbedded keepend

" ── Structural elements ──────────────────────────────────────
syn match lobSeparator  /^---$/
syn match lobSubHead    /^##.*$/
syn match lobModHead    /^#[^#].*$/
syn match lobSectionHead /^#\(Tests\|Binding\|References\|Appendix\)\s*$/
syn match lobSigil      /^\~\S\+.*/

" ── Highlight links ──────────────────────────────────────────
hi def link lobModHead      Title
hi def link lobSubHead      Type
hi def link lobSectionHead  PreProc
hi def link lobSigil        Keyword
hi def link lobSeparator    Comment

let b:current_syntax = "lob"
