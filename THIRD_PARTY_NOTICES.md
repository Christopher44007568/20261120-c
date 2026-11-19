# Third-party notices

## three.js LTC texture data

`src/ltc-data.bin` is generated from the `LTC_MAT_1` and `LTC_MAT_2` arrays in
three.js `examples/jsm/lights/RectAreaLightTexturesLib.js` at tag `r170`.

Three.js is distributed under the MIT License:
<https://github.com/mrdoob/three.js/blob/r170/LICENSE>

The data implements the fitted linearly transformed cosine (LTC) approximation
described in:

Eric Heitz, Jonathan Dupuy, Stephen Hill, and David Neubelt.
"Real-Time Polygonal-Light Shading with Linearly Transformed Cosines."
ACM Transactions on Graphics 35(4), 2016.

Reference implementation and fitted data:
<https://github.com/selfshadow/ltc_code>
