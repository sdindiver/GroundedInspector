Add 1-3 exemplar images of WHITE_MARK here (global defect; applies to every part).
The assembler globs *.jpg/*.png in this folder; filenames can be anything.

white_mark = a LOCALISED, dull, LOW-luster patch where the finish has lost shine
but the brushed grain is still visible through it; it does NOT shift with viewing
angle. Show the dull patch clearly so the API learns it vs:
  - GLARE / specular highlight: BRIGHTER + grain-free + moves with angle (not a defect);
  - the uniform whole-face rainbow passivation TINT: covers the entire face evenly
    (that is the finish, not a defect).
Only a localised dull patch that contrasts with the rest of the SAME face is a
white_mark. For the bracket, 165247 is the ground-truth white_mark sample.
