import sys
import types
import torch
import torch.nn.modules.linear as linear

if not hasattr(linear, "_LinearWithBias"):
    linear._LinearWithBias = torch.nn.Linear

if "torch._six" not in sys.modules:
    import collections.abc

    six_mod = types.ModuleType("torch._six")
    six_mod.container_abcs = collections.abc
    six_mod.int_classes = (int,)
    six_mod.string_classes = (str,)
    six_mod.FileNotFoundError = FileNotFoundError
    sys.modules["torch._six"] = six_mod

from timesformer.models.vit import TimeSformer

raw = torch.load("lexius_accident_v1_e10.pth", map_location="cpu")
state = raw

model = TimeSformer(
    img_size=224,
    patch_size=16,
    num_classes=2,
    num_frames=16,
    attention_type="divided_space_time",
)
missing, unexpected = model.load_state_dict(state, strict=False)
print("missing", len(missing))
print("unexpected", len(unexpected))
print("missing_sample", missing[:10])
print("unexpected_sample", unexpected[:10])
print("load_ok")
