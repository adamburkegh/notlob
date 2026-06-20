" Vim filetype plugin for notlob literate programming (.lob)

if exists("b:did_ftplugin")
  finish
endif
let b:did_ftplugin = 1

setlocal shiftwidth=4
setlocal expandtab
setlocal textwidth=80

let b:undo_ftplugin = "setl sw< et< tw<"
