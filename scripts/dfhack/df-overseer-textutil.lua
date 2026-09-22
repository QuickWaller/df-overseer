-- df-overseer-textutil.lua
--@module = true
--
-- Single shared helper for converting DF's CP437-encoded game text to UTF-8
-- before it reaches this project's JSON output or the Python side of dfmcp.
--
-- WHY THIS EXISTS (handoffs/2026-09-22-loop-game-text-encoding.md): DF
-- stores game text -- procedurally generated names, job names, building/
-- zone/burrow names, race names, announcement/report text, noble position
-- titles, anything read off a df.* string field -- in CP437, not UTF-8.
-- dfmcp's Python side decodes tool output as UTF-8
-- (dfmcp/dfhack_client.py). `diff.since` crashed the conductor's first
-- cycle (`'utf-8' codec can't decode byte 0x96'`) on a dwarf name holding a
-- CP437 accented character, because df-overseer-diff.lua put
-- dfhack.translation.translateName(...)'s raw CP437 bytes straight into its
-- JSON output with no conversion. This was never a single call site's bug:
-- before this file, no script under scripts/dfhack/ called dfhack.df2utf
-- anywhere, so every tool that prints a name, a job, an item description,
-- an announcement or any other game string could hit the same crash the
-- moment a generated name held a non-ASCII CP437 byte.
--
-- dfhack.df2utf(string) is documented ("Convert a string from DF's CP437
-- encoding to UTF-8.", hack/docs/docs/dev/Lua API.txt) and is the standard
-- idiom this DFHack version's own shipped scripts use for every game-text
-- field: hack/scripts/exportlegends.lua wraps EVERY name/description/title
-- it emits with dfhack.df2utf unconditionally, including plain-ASCII ones
-- (item subtype names, race names, job/profession enum labels via
-- df_enums), so wrapping an already-ASCII string is this DFHack install's
-- own existing, load-bearing pattern, not a guess. This project has not
-- independently unit-tested dfhack.df2utf's C++ behaviour against a known
-- input on this install; exportlegends.lua's unconditional-wrap usage is
-- the evidence for "safe on ASCII", not a live probe run for this stream
-- (mark this ASSUMED, not verified against the install directly).
--
-- USAGE: call to_utf8(s) at the SOURCE of every game-text value -- where it
-- is first read off a df.* field or returned by a dfhack.translation.*/
-- units.*/job.*/buildings.*/burrows.* name accessor -- before it goes into
-- a table this script returns, or before print/json.encode sees it. Keys
-- and enum names this project's own Lua writes (not read from the game) do
-- NOT need conversion, e.g. `type = "JOB_COMPLETED"`, a category tag, a
-- role name, a doctrine key: the difference is game-authored text (a
-- dwarf's generated name, a raw's item description, an announcement
-- sentence) versus script-authored text (an identifier this repo's own Lua
-- chose).
--
-- No CLI dispatch: this file exports one function and nothing else, so
-- there is nothing to guard with the `if dfhack_flags.module then return
-- end` pattern the other df-overseer-*.lua scripts use (their guard exists
-- to skip CLI-dispatch code during a reqscript module load; this file has
-- none to skip). reqscript('df-overseer-textutil') picks up to_utf8 the
-- same way reqscript('df-overseer-landmarks') picks up nearest_landmark: a
-- non-local function becomes a field on the table reqscript returns.

-- Convert one game-text string to UTF-8. Safe on nil, non-string and empty
-- input (returned unchanged); on a df2utf failure (pcall guards the C++
-- call, matching this project's existing pattern for every other DFHack
-- accessor), the original string is returned rather than raising, so a
-- caller never crashes because of this helper -- the Python-side backstop
-- (dfmcp/dfhack_client.py) is the last line of defence if a raw CP437 byte
-- still gets through.
function to_utf8(s)
  if type(s) ~= "string" or s == "" then
    return s
  end
  local ok, out = pcall(dfhack.df2utf, s)
  if ok and type(out) == "string" then
    return out
  end
  return s
end
