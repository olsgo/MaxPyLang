# MaxPyLang

[![CI](https://github.com/Barnard-PL-Labs/MaxPy-Lang/actions/workflows/ci.yml/badge.svg)](https://github.com/Barnard-PL-Labs/MaxPy-Lang/actions/workflows/ci.yml)

MaxPyLang is a Python package for metaprogramming of MaxMSP that uses Python to generate and edit Max patches. MaxPyLang allows users to move freely between text-based Python programming and visual programming in Max, making it much easier to implement dynamic patches, random patches, mass-placement and mass-connection of objects, and other easily text-programmed techniques.

As a text-based interface to MaxMSP, MaxPyLang enables vibecoding of Max patches. Provide an example to your tool of choice (Claude code, Cursor, etc), and ask for the patch you would like. Tutorial coming soon.

## Installation

We publish our package on Pypi as [MaxPyLang](https://pypi.org/project/maxpylang/). It is easiest to install from there.

```bash
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install maxpylang
```

## Documentation
- [Full Documentation](https://barnard-pl-labs.github.io/MaxPyLang/)
- [API Reference](https://barnard-pl-labs.github.io/MaxPyLang/API/API.html)
- [Examples](https://github.com/Barnard-PL-Labs/MaxPyLang/tree/main/examples)
- [Tutorials](https://barnard-pl-labs.github.io/MaxPyLang/tutorial.html)

## Quick Start

See this example in [examples/hello_world](./examples/hello_world).
To run this, `python3 examples/hello_world/main.py` will create a Max patch file `hello_world.maxpat` that contains a simple audio oscillator connected to the DAC.
You can then open this patch in MaxMSP and click the DAC to hear a 440 Hz tone.

```python
import maxpylang as mp

patch = mp.MaxPatch()
osc = patch.place("cycle~ 440")[0]
dac = patch.place("ezdac~")[0]
patch.connect([osc.outs[0], dac.ins[0]])
patch.save("hello_world.maxpat")
```

## CLI Quick Start

MaxPyLang now ships with a CLI command named `maxpylang`.

```bash
# Create a new patch
maxpylang new --out patch.maxpat

# Place two objects into that patch
maxpylang --in-place place --in patch.maxpat \
  --obj "cycle~ 440" \
  --obj "ezdac~"

# Connect object outlet/inlet pairs
maxpylang --in-place connect --in patch.maxpat \
  --edge "obj-1:0->obj-2:0" \
  --edge "obj-1:0->obj-2:1"

# Equivalent connect syntax using --from/--to pairs
maxpylang --in-place connect --in patch.maxpat \
  --from "obj-1:0" --to "obj-2:0" \
  --from "obj-1:0" --to "obj-2:1"

# Check for unknown/unlinked objects
maxpylang check --in patch.maxpat

# Export a Max for Live device file (.amxd), skip runtime validation when needed
maxpylang export-amxd --in patch.maxpat --out device.amxd --no-validate
```

For automation, add `--json` to return structured command output.
In JSON mode, CLI output is guaranteed to be JSON-only on stdout.
Each JSON payload includes:
- `schema_version` for envelope compatibility
- `schema` for command success/error schema id
- `data_schema` for command-specific data payload schema id
- `generated_at` timestamp
- `diagnostics` for captured internal log lines that would otherwise pollute stdout

`export-amxd` validates by default by opening the exported file in Max and waiting for an auto-save roundtrip.
Current validation runtime support is macOS with a local Max installation.

## Citation

MaxPy was published as a [demo paper](examples/NIME2023/MaxPy-NIME-2023-Paper.pdf) for NIME 2023.
The package name was updated to MaxPyLang in 2025 to avoid confusion with other similarly named packages.

## Video Demos 
### [Basics](https://www.youtube.com/watch?v=F8Fpe0Udc4M)      
[![Introduction to MaxPy](https://img.youtube.com/vi/F8Fpe0Udc4M/0.jpg)](https://www.youtube.com/watch?v=F8Fpe0Udc4M)     
Mark demonstrates the basics of installing MaxPy, creating patches, and placing objects.   
<br>
### [Variable-Oscillator Synth](https://www.youtube.com/watch?v=nxusu32kkxs)       
[![Variable-Oscillator Synth Explanation](https://img.youtube.com/vi/nxusu32kkxs/0.jpg)](https://www.youtube.com/watch?v=nxusu32kkxs)      
Ranger explains a MaxPy script that dynamically generates an additive synth with a variable number of oscillators. The code for this synth is under [examples/variable-osc-synth](examples/variable-osc-synth). 
<br>
### [Replace() function]((https://youtu.be/RgYRqXn8Z6o))       
[![Using Replace() function with MaxPy](https://img.youtube.com/vi/RgYRqXn8Z6o/0.jpg)](https://youtu.be/RgYRqXn8Z6o)      
Satch explains using the replace() function to selectively replace objects in a loaded patch to sonify stock data. The code for this is under [examples/stocksonification_v1](examples/stocksonification_v1). 
