# aconfgen

Generate a complete default Alacritty TOML configuration by parsing the
Alacritty configuration and default-bindings manpages.

```text
aconfgen --platform linux
aconfgen --platform macos --output alacritty.toml
aconfgen parse > alacritty-ir.json
```


the required manpages are available from:

base manpage: https://raw.githubusercontent.com/alacritty/alacritty/refs/heads/master/extra/man/alacritty.5.scd
bindings: https://raw.githubusercontent.com/alacritty/alacritty/refs/heads/master/extra/man/alacritty-bindings.5.scd
