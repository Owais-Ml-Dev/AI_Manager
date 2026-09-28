#include <flutter/runtime_effect.glsl>

precision highp float;

uniform vec2 uSize;
uniform float uTime;
uniform float uLevel;
uniform float uSpeaking;
uniform float uMuted;
uniform float uFailed;

out vec4 fragColor;


// ------------------------------------------------------------
// BASIC HELPERS
// ------------------------------------------------------------

float hash21(vec2 p) {
    p = fract(
        p * vec2(
            123.34,
            456.21
        )
    );

    p += dot(
        p,
        p + 45.32
    );

    return fract(
        p.x * p.y
    );
}


float noise21(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);

    f = f * f * (
        3.0 - 2.0 * f
    );

    float a = hash21(i);
    float b = hash21(
        i + vec2(1.0, 0.0)
    );
    float c = hash21(
        i + vec2(0.0, 1.0)
    );
    float d = hash21(
        i + vec2(1.0, 1.0)
    );

    return mix(
        mix(a, b, f.x),
        mix(c, d, f.x),
        f.y
    );
}


float fbm(vec2 p) {
    float value = 0.0;
    float amplitude = 0.5;

    for (
        int i = 0;
        i < 4;
        i++
    ) {
        value +=
            amplitude *
            noise21(p);

        p =
            p * 2.03 +
            vec2(
                17.17,
                9.23
            );

        amplitude *= 0.5;
    }

    return value;
}


// ------------------------------------------------------------
// DOTTED / PARTICLE GRID
// ------------------------------------------------------------

float particleField(
    vec2 p,
    float density,
    float radius
) {
    vec2 grid =
        p * density;

    vec2 cell =
        floor(grid);

    vec2 local =
        fract(grid) -
        0.5;

    float randomValue =
        hash21(cell);

    vec2 jitter =
        vec2(
            hash21(
                cell + 3.7
            ),
            hash21(
                cell + 8.1
            )
        ) -
        0.5;

    local -=
        jitter * 0.34;

    float d =
        length(local);

    float point =
        smoothstep(
            radius,
            radius * 0.15,
            d
        );

    return point *
        (
            0.55 +
            randomValue * 0.45
        );
}


// ------------------------------------------------------------
// MAIN
// ------------------------------------------------------------

void main() {
    vec2 frag =
        FlutterFragCoord().xy;

    vec2 uv =
        (
            frag -
            0.5 * uSize
        ) /
        min(
            uSize.x,
            uSize.y
        );

    float time =
        uTime;

    float audio =
        clamp(
            uLevel,
            0.0,
            1.0
        );

    if (
        uMuted > 0.5
    ) {
        audio *= 0.12;
    }


    // --------------------------------------------------------
    // DEFORMED CIRCULAR OUTLINE
    // --------------------------------------------------------

    float angle =
        atan(
            uv.y,
            uv.x
        );

    float radial =
        length(uv);

    float waveA =
        sin(
            angle * 7.0 +
            time * 1.7
        );

    float waveB =
        sin(
            angle * 13.0 -
            time * 1.2
        );

    float waveC =
        sin(
            angle * 21.0 +
            time * 0.75
        );

    float organicNoise =
        fbm(
            vec2(
                angle * 1.8 +
                time * 0.08,
                time * 0.11
            )
        ) -
        0.5;

    float speakingBoost =
        mix(
            1.0,
            1.30,
            uSpeaking
        );

    float deformation =
        (
            waveA * 0.012 +
            waveB * 0.007 +
            waveC * 0.003 +
            organicNoise * 0.022
        ) *
        (
            0.35 +
            audio * 1.75
        ) *
        speakingBoost;

    float sphereRadius =
        0.325 +
        deformation;

    float sphereDistance =
        radial -
        sphereRadius;


    // --------------------------------------------------------
    // SPHERE MASK
    // --------------------------------------------------------

    float sphere =
        1.0 -
        smoothstep(
            -0.006,
            0.008,
            sphereDistance
        );


    // --------------------------------------------------------
    // FAKE 3D SPHERE DEPTH
    // --------------------------------------------------------

    float normalizedRadius =
        clamp(
            radial /
            max(
                sphereRadius,
                0.001
            ),
            0.0,
            1.0
        );

    float z =
        sqrt(
            max(
                0.0,
                1.0 -
                normalizedRadius *
                normalizedRadius
            )
        );

    vec3 normal =
        normalize(
            vec3(
                uv.x,
                uv.y,
                z * 0.50
            )
        );

    vec3 lightDirection =
        normalize(
            vec3(
                -0.45,
                -0.55,
                0.90
            )
        );

    float diffuse =
        max(
            dot(
                normal,
                lightDirection
            ),
            0.0
        );

    float fresnel =
        pow(
            1.0 -
            z,
            2.4
        );


    // --------------------------------------------------------
    // PARTICLE MESH
    // --------------------------------------------------------

    vec2 curvedUV =
        uv;

    curvedUV.x +=
        sin(
            curvedUV.y * 17.0 +
            time * 0.75
        ) *
        (
            0.006 +
            audio * 0.009
        );

    curvedUV.y +=
        cos(
            curvedUV.x * 15.0 -
            time * 0.62
        ) *
        (
            0.006 +
            audio * 0.010
        );

    float particlesFine =
        particleField(
            curvedUV,
            102.0,
            0.20
        );

    float particlesMid =
        particleField(
            curvedUV +
            vec2(
                time * 0.002,
                -time * 0.001
            ),
            68.0,
            0.16
        );

    float meshWave =
        sin(
            curvedUV.x * 95.0 +
            sin(
                curvedUV.y * 38.0 +
                time
            ) * 3.0 +
            time * 1.6
        );

    meshWave =
        smoothstep(
            0.74,
            1.0,
            meshWave
        );

    float mesh =
        (
            particlesFine * 0.72 +
            particlesMid * 0.38 +
            meshWave * 0.16
        ) *
        sphere;


    // --------------------------------------------------------
    // DEFORMING OUTER PARTICLE EDGE
    // --------------------------------------------------------

    float edge =
        exp(
            -abs(
                sphereDistance
            ) * 135.0
        );

    float edgeDots =
        particleField(
            vec2(
                angle * 0.72,
                radial * 5.0 +
                time * 0.03
            ),
            64.0,
            0.21
        );

    edge *=
        0.55 +
        edgeDots * 1.25;


    // --------------------------------------------------------
    // INNER ENERGY MOTION
    // --------------------------------------------------------

    float innerNoise =
        fbm(
            curvedUV * 8.0 +
            vec2(
                time * 0.12,
                -time * 0.09
            )
        );

    float energyBand =
        sin(
            curvedUV.y * 30.0 +
            curvedUV.x * 13.0 +
            time * 2.0
        );

    energyBand =
        smoothstep(
            0.55,
            1.0,
            energyBand
        );

    energyBand *=
        sphere *
        (
            0.08 +
            audio * 0.42
        );


    // --------------------------------------------------------
    // GREY / BLACK COLOR SYSTEM
    // --------------------------------------------------------

    vec3 background =
        vec3(
            0.0
        );

    vec3 darkSphere =
        vec3(
            0.028,
            0.030,
            0.034
        );

    vec3 middleGrey =
        vec3(
            0.30,
            0.31,
            0.33
        );

    vec3 brightGrey =
        vec3(
            0.86,
            0.88,
            0.91
        );

    vec3 white =
        vec3(
            0.98
        );


    if (
        uFailed > 0.5
    ) {
        middleGrey =
            vec3(
                0.46,
                0.12,
                0.12
            );

        brightGrey =
            vec3(
                1.0,
                0.25,
                0.22
            );

        white =
            vec3(
                1.0,
                0.35,
                0.30
            );
    }


    vec3 sphereColor =
        darkSphere;

    sphereColor +=
        middleGrey *
        diffuse *
        0.10;

    sphereColor +=
        brightGrey *
        fresnel *
        0.13;


    // Dense point cloud.
    sphereColor +=
        mix(
            middleGrey,
            brightGrey,
            diffuse
        ) *
        mesh *
        (
            0.36 +
            audio * 0.52
        );


    // Internal animated activity.
    sphereColor +=
        brightGrey *
        innerNoise *
        0.055 *
        sphere;

    sphereColor +=
        white *
        energyBand *
        0.15;


    // Strong luminous rim.
    vec3 rimColor =
        mix(
            brightGrey,
            white,
            0.60 +
            audio * 0.40
        );

    sphereColor +=
        rimColor *
        edge *
        (
            0.58 +
            audio * 1.10
        );


    // --------------------------------------------------------
    // SOFT EXTERNAL GLOW
    // --------------------------------------------------------

    float glow =
        exp(
            -abs(
                sphereDistance
            ) * 34.0
        ) *
        (
            0.10 +
            audio * 0.14
        );

    vec3 finalColor =
        background;

    finalColor +=
        sphereColor *
        sphere;

    finalColor +=
        brightGrey *
        glow;


    // --------------------------------------------------------
    // FADE OUT FAR FROM SPHERE
    // --------------------------------------------------------

    float overallMask =
        1.0 -
        smoothstep(
            0.40,
            0.49,
            radial
        );

    finalColor *=
        overallMask;


    fragColor =
        vec4(
            finalColor,
            clamp(
                max(
                    sphere,
                    glow * 2.4
                ),
                0.0,
                1.0
            )
        );
}
