#version 440
// Bent°Corner loading card (Oliver, 31.10.2026 – labs/loading-anim/ladeanimation.html, draft d4 with his values).
// One card at a time: laid down from the front (large -> 1, fading in), tilted, folded at a random corner; the flap
// swings back around the fold edge (back grey, front card colour, inner corner r = 5) while the card straightens up
// with an overshoot (outBack); then a double-stripe glint top left -> bottom right; then it fades and sinks back
// (gap), only then the next one. The first card is the logo without ring (top right, F = 21, -7°) – its values are a
// brand asset (brand/loadcard.json via loadCard; w = 0 without brand/: the first card is random like the others).
// Everything is computed here from "time" (a UniformAnimator on the render thread) – it keeps moving while Python
// works on the GUI thread. Card space: 100 units (card x 25..75, y 15..85, r = 5), the item shows 130 units.
// Compile: pyside6-qsb --qt6 -o loadcard.frag.qsb loadcard.frag

layout(location = 0) in vec2 qt_TexCoord0;
layout(location = 0) out vec4 fragColor;
layout(std140, binding = 0) uniform buf {
    mat4 qt_Matrix;
    float qt_Opacity;
    float time;      // seconds since the loading sign appeared
    float still;     // 1 = still picture: the logo card (-7°, flap folded over) – animations off, tiny sizes
    float dark;      // 1 = dark look
    vec4 cardColor;  // hsl(240 3% 50%)
    vec4 tabColor;   // back of the flap
    float leave;     // 0..1 over GAP: loading is done – the card sinks away now (while the screen fades out)
    vec4 loadCard;   // the first card (brand/loadcard.json): corner, fold, tilt, w = 1 – w = 0: random
};

// Oliver's values (werte-oliver-2026-10-31.json)
const float ENTER = 0.3, UNFOLD_AT = 0.25, UNFOLD = 0.55, SHIM_AT = 0.9, SHIM = 0.75, NEXT = 1.6, GAP = 0.3;
const float START_SCALE = 1.28, LEAVE_SHRINK = 0.22, OVERSHOOT = 2.2, TILT_MAX = 20.0, FOLD_MAX = 35.0;
const float SHADE = 0.18, FLAP_SHADE = 1.0, GLINT = 1.15, GLINT_W = 1.4;
const float X0 = 25.0, X1 = 75.0, Y0 = 15.0, Y1 = 85.0, R = 5.0, VIEW = 130.0, PI = 3.14159265;

float clamp01(float t) { return clamp(t, 0.0, 1.0); }
float outCubic(float t) { return 1.0 - pow(1.0 - t, 3.0); }
float inOutSine(float t) { return -(cos(PI * t) - 1.0) / 2.0; }
float outBack(float t, float s) { return 1.0 + (s + 1.0) * pow(t - 1.0, 3.0) + s * pow(t - 1.0, 2.0); }
float hash(float n) { return fract(sin(n * 127.1 + 311.7) * 43758.5453); }

// coverage of an implicit edge f (< 0 inside), anti-aliased over one pixel
float cover(float f) { return clamp(0.5 - f / max(fwidth(f), 1e-4), 0.0, 1.0); }

float sdRoundBox(vec2 p, vec2 c, vec2 h, float r) {
    vec2 q = abs(p - c) - h + r;
    return length(max(q, 0.0)) + min(max(q.x, q.y), 0.0) - r;
}

// card outline, its top-right corner cut by the fold edge (F = 0: whole card)
float cardSd(vec2 q, float F) {
    float d = sdRoundBox(q, vec2(50.0, 50.0), vec2(25.0, 35.0), R);
    if (F > 0.01) d = max(d, ((q.x - (X1 - F)) - (q.y - Y0)) * 0.70710678);
    return d;
}

float cross2(vec2 a, vec2 b) { return a.x * b.y - a.y * b.x; }

// flap: triangle A, B, tip with the tip rounded by a quadratic curve tb -> ta (control point tip)
float flapCover(vec2 q, vec2 A, vec2 B, vec2 tip, float r) {
    float s = sign(cross2(B - A, tip - A));
    if (abs(cross2(B - A, tip - A)) < 1e-3) return 0.0;   // edge-on
    float e1 = s * cross2(B - A, q - A), e2 = s * cross2(tip - B, q - B), e3 = s * cross2(A - tip, q - tip);
    float inside = min(cover(-e1 / length(B - A)), min(cover(-e2 / length(tip - B)), cover(-e3 / length(A - tip))));
    vec2 ta = tip + normalize(A - tip) * r, tb = tip + normalize(B - tip) * r;
    // barycentric coordinates in the small triangle (tb, tip, ta); outside the curve: (l1/2)^2 > l0*l2
    float area = cross2(tip - tb, ta - tb);
    if (abs(area) < 1e-4) return inside;
    float l1 = cross2(q - tb, ta - tb) / area;
    float l2 = cross2(tip - tb, q - tb) / area;
    float l0 = 1.0 - l1 - l2;
    if (l0 >= 0.0 && l1 >= 0.0 && l2 >= 0.0) {
        float f = l1 * l1 * 0.25 - l0 * l2;   // > 0 between the curve and the tip: not part of the flap
        inside *= cover(f);
    }
    return inside;
}

vec4 over(vec4 dst, vec3 col, float a) { return vec4(col * a + dst.rgb * (1.0 - a), a + dst.a * (1.0 - a)); }

void main() {
    // which card, how far
    float T = still > 0.5 ? ENTER : max(time, 0.0);   // still: the logo card laid down, flap still folded over
    float period = NEXT + GAP;
    float k = floor(T / period);
    float t = T - k * period;
    float corner = loadCard.x, F = loadCard.y, rot = loadCard.z;   // the first card: the logo (brand/)
    if (k > 0.5 || loadCard.w < 0.5) {
        corner = floor(hash(k) * 4.0);
        F = mix(min(15.0, FOLD_MAX), FOLD_MAX, hash(k + 17.0));
        rot = (hash(k + 41.0) < 0.5 ? -1.0 : 1.0) * mix(min(5.0, TILT_MAX), TILT_MAX, hash(k + 73.0));
    }
    float enter = outCubic(clamp01(t / ENTER));
    float u = still > 0.5 ? 0.0 : clamp01((t - UNFOLD_AT) / UNFOLD);
    float unf = inOutSine(u);
    float str = outBack(u, OVERSHOOT);
    float shim = still > 0.5 ? 0.0 : clamp01((t - SHIM_AT) / SHIM);
    float alpha = enter, sc = START_SCALE - (START_SCALE - 1.0) * enter;
    float l = still < 0.5 && t > NEXT ? inOutSine(clamp01((t - NEXT) / GAP)) : 0.0;   // fades and sinks back, then the next one
    l = max(l, inOutSine(clamp01(leave)));                    // or now, because loading is done
    alpha *= 1.0 - l; sc *= 1.0 - LEAVE_SHRINK * l;
    if (alpha <= 0.001) { fragColor = vec4(0.0); return; }
    float a = radians(rot * (1.0 - str));

    // screen point -> card space (unmirrored P) -> local space with the fold top right (Q)
    vec2 s = (qt_TexCoord0 - 0.5) * VIEW;
    vec2 p = vec2(cos(a) * s.x + sin(a) * s.y, -sin(a) * s.x + cos(a) * s.y) / sc + 50.0;
    vec2 m = vec2((corner == 0.0 || corner == 3.0) ? -1.0 : 1.0, (corner == 2.0 || corner == 3.0) ? -1.0 : 1.0);
    vec2 q = 50.0 + m * (p - 50.0);

    bool isFlat = unf >= 0.999;
    vec3 fg = cardColor.rgb;
    vec4 col = vec4(0.0);
    float body = cover(cardSd(q, isFlat ? 0.0 : F));
    col = over(col, fg, body);
    vec2 d = vec2(X1 - X0, Y1 - Y0);   // soft shade: light top left -> darker bottom right
    col = over(col, vec3(0.0), body * SHADE * clamp01(dot(q - vec2(X0, Y0), d) / dot(d, d)));

    if (!isFlat) {   // the flap swings around the hinge A-B: tip from the mirrored corner (back up) to the real corner
        vec2 A = vec2(X1 - F, Y0), B = vec2(X1, Y0 + F), Mid = (A + B) * 0.5, inner = vec2(X1 - F, Y0 + F);
        float kk = cos(PI * unf);
        vec2 tip = Mid + (inner - Mid) * kk;
        bool back = kk > 0.0;
        float r = min(R, 0.45 * length(tip - A));
        // the flap always lies within the whole card – nearly edge-on its triangle collapses onto the hinge line and
        // every point of that line (far beyond the card) would get half coverage: a hairline through the picture
        float fl = flapCover(q, A, B, tip, r) * cover(cardSd(q, 0.0) - 1.0);
        col = over(col, back ? tabColor.rgb : fg, fl);
        float up = 1.0 - abs(kk);
        col = over(col, back ? vec3(0.0) : vec3(1.0), fl * (back ? 0.25 : 0.5) * up * FLAP_SHADE);
        if (!back) {   // close the hairline seam along the hinge
            float seam = abs(cross2(normalize(B - A), q - A)) - 0.3;
            col = over(col, fg, cover(seam) * cover(cardSd(q, 0.0)));
        }
    }

    if (shim > 0.0 && shim < 1.0) {   // double-stripe glint, always top left -> bottom right of the screen
        float inCard = cover(cardSd(p, 0.0));
        vec2 g0 = vec2(X0 - 10.0, Y0 - 14.0), g1 = vec2(X1 + 10.0, Y1 + 14.0);
        float g = clamp01(dot(p - g0, g1 - g0) / dot(g1 - g0, g1 - g0));
        float ps = inOutSine(shim), sh = -0.25 + 1.5 * ps, am = sin(PI * shim);
        float light = (dark > 0.5 ? 1.0 : 0.75) * GLINT, w = GLINT_W;
        float off[6] = float[](sh - 0.12 * w, sh - 0.075 * w, sh - 0.03 * w, sh + 0.005 * w, sh + 0.03 * w, sh + 0.055 * w);
        float val[6] = float[](0.0, light * am, 0.0, 0.0, light * 0.9 * am, 0.0);
        // like a canvas gradient: only stops inside 0..1, padded with the first/last of them
        float v = 0.0; bool anyStop = false; float po = 0.0, pv = 0.0; float first = 0.0, last = 0.0; bool done = false;
        for (int i = 0; i < 6; i++) {
            if (off[i] <= 0.0 || off[i] >= 1.0) continue;
            if (!anyStop) { anyStop = true; first = val[i]; if (g <= off[i]) { v = val[i]; done = true; } }
            else if (!done && g <= off[i]) { v = mix(pv, val[i], (g - po) / max(off[i] - po, 1e-5)); done = true; }
            po = off[i]; pv = val[i]; last = val[i];
        }
        if (anyStop && !done) v = last;
        col = over(col, vec3(1.0), inCard * min(1.0, v));
    }
    fragColor = col * alpha * qt_Opacity;
}
