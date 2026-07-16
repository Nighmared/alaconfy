# Types:

- String `_<string>_`
- Literals (`_"lala"_`)
- Int `_<integer>_`
- bool: `_true_ | _false_ `
- Union: `_"OnlyLeft"_ | _"OnlyRight"_ | _"Both"_`
- Maps/Objects: `{ key1 = type1, key2 = type2 }`
- lists: `[type1, type2, type3,]` (trailing comma (but not always..)!)

# section start

`# ALLCAPS`

# entry

`*key* = type`

# subsection start

`*tablename*`

End of subsection can only be determined by reduced indentation of next line, meaning we have to peek ahead while parsing instead of consuming directly

# subsection entry

`    *key* = type` (leading tab)

# Default

This is present for every entry,
below the entry line there are optionally one or more lines of documentation, at some point there _MUST_ be a line that follows this pattern:

`   Default: <value of correct type>`

> Note the indentation. This means for subsection entries the default is defined as follows:

`        Default: <value of correct type>` (2 tabs)

# Implementation Bumpyness

- do we even need the types?
- parsing anything but base types will be funi (recursive object/list parsing whoop whoop) (so, again, do we need the types?)
- for `font.normal`, `terminal.shell`, there are multiple defaults (for different OSs) and specified in a different way to the others
- `colors` is the only section with subtables, but should still be generally supported
