/**
 * GLSL shaders for the forest scene. Kept as plain strings (not .glsl files
 * with a loader) so the 3D components have zero extra build configuration.
 */

/** Instanced canopy foliage: each instance sways with a wind field that
 * varies by world position (so trees do not all sway in perfect unison) and
 * by height within the tree (canopy tips move more than the trunk). */
export const canopyVertexShader = /* glsl */ `
  uniform float uTime;
  uniform float uWindStrength;

  attribute vec3 instanceOffset;
  attribute float instancePhase;
  attribute float instanceScale;

  varying vec3 vColor;
  varying float vHeight;

  void main() {
    vec3 transformed = position * instanceScale;

    // Sway increases with height so the canopy top moves more than its base —
    // an approximation of how a real tree bends under wind load.
    float heightFactor = clamp((transformed.y + 1.0) * 0.5, 0.0, 1.0);
    float wind = sin(uTime * 0.6 + instancePhase + instanceOffset.x * 0.15)
               * cos(uTime * 0.35 + instanceOffset.z * 0.2);
    transformed.x += wind * uWindStrength * heightFactor * heightFactor;
    transformed.z += wind * uWindStrength * 0.6 * heightFactor * heightFactor;

    vec3 worldPosition = transformed + instanceOffset;
    vHeight = heightFactor;
    vColor = color;

    vec4 mvPosition = modelViewMatrix * vec4(worldPosition, 1.0);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

export const canopyFragmentShader = /* glsl */ `
  uniform float uTime;
  uniform vec3 uDeepColor;
  uniform vec3 uLitColor;

  varying vec3 vColor;
  varying float vHeight;

  void main() {
    vec3 base = mix(uDeepColor, uLitColor, vHeight);
    vec3 tinted = base * (0.75 + 0.25 * vColor.g);
    gl_FragColor = vec4(tinted, 1.0);
  }
`;

/** Ground mist: a slowly-scrolling, softly-clipped noise band near y=0. */
export const mistVertexShader = /* glsl */ `
  varying vec2 vUv;
  void main() {
    vUv = uv;
    gl_Position = projectionMatrix * modelViewMatrix * vec4(position, 1.0);
  }
`;

export const mistFragmentShader = /* glsl */ `
  uniform float uTime;
  uniform vec3 uColor;
  varying vec2 vUv;

  float hash(vec2 p) {
    return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453123);
  }

  float noise(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    float a = hash(i);
    float b = hash(i + vec2(1.0, 0.0));
    float c = hash(i + vec2(0.0, 1.0));
    float d = hash(i + vec2(1.0, 1.0));
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(a, b, u.x) + (c - a) * u.y * (1.0 - u.x) + (d - b) * u.x * u.y;
  }

  void main() {
    vec2 p = vUv * vec2(6.0, 2.0) + vec2(uTime * 0.02, uTime * 0.008);
    float n = noise(p) * 0.6 + noise(p * 2.1 + 4.0) * 0.4;
    float edge = smoothstep(0.0, 0.35, vUv.y) * smoothstep(1.0, 0.55, vUv.y);
    float alpha = n * edge * 0.35;
    gl_FragColor = vec4(uColor, alpha);
  }
`;

/** Firefly point sprites: soft radial glow, gentle size pulse. */
export const fireflyVertexShader = /* glsl */ `
  uniform float uTime;
  attribute float aPhase;
  attribute float aSize;
  varying float vPulse;

  void main() {
    vPulse = 0.5 + 0.5 * sin(uTime * 1.8 + aPhase);
    vec4 mvPosition = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = aSize * (200.0 / -mvPosition.z) * (0.6 + 0.4 * vPulse);
    gl_Position = projectionMatrix * mvPosition;
  }
`;

export const fireflyFragmentShader = /* glsl */ `
  uniform vec3 uColor;
  varying float vPulse;

  void main() {
    vec2 centered = gl_PointCoord - vec2(0.5);
    float dist = length(centered);
    float glow = smoothstep(0.5, 0.0, dist);
    gl_FragColor = vec4(uColor, glow * (0.35 + 0.65 * vPulse));
  }
`;
