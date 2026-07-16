# aconfgen

Generate a complete default Alacritty TOML configuration by parsing the
Alacritty configuration and default-bindings manpages.

```text
aconfgen --platform linux
aconfgen --platform macos --output alacritty.toml
aconfgen parse > alacritty-ir.json
```



## the required manpages are available from:

base manpage: https://raw.githubusercontent.com/alacritty/alacritty/refs/heads/master/extra/man/alacritty.5.scd

bindings: https://raw.githubusercontent.com/alacritty/alacritty/refs/heads/master/extra/man/alacritty-bindings.5.scd

## Disclaimer

I usually take pride in writing good code. However since I did not feel that this was worth my time and effort, this project was implemented entirely by AI. Using a Skill distilled from another project to simulate my own coding style and some basic guidance about how the parser should be built.

## Why is this even needed?

See [this pr](https://github.com/alacritty/alacritty/issues/6999) for weirdly intense opinions about manpages and config files.
