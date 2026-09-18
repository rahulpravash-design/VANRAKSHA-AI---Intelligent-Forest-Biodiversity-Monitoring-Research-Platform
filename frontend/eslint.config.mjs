import nextConfig from "eslint-config-next";

const eslintConfig = [
  ...nextConfig,
  {
    // react-three-fiber's entire model is imperative mutation of Three.js
    // objects inside useFrame — that is how it avoids re-rendering the React
    // tree at 60fps. eslint-plugin-react-hooks' newer rules assume every
    // component follows the React Compiler's pure-render model, which r3f
    // deliberately does not: `useThree().camera`, mesh refs, and shader
    // uniforms are meant to be mutated outside React's render cycle. This
    // exception is scoped to the 3D component directory only; nothing in
    // src/app or the rest of src/components should trip these rules.
    files: ["src/components/three/**/*.{ts,tsx}"],
    rules: {
      "react-hooks/immutability": "off",
    },
  },
  {
    // useAsync's setLoading(true) / setError(null) at the top of the fetch
    // effect is the standard shape of a manual data-fetching hook: it must
    // reset to a fresh loading state the moment the effect's dependencies
    // change, before the async call resolves, or a refetch would show stale
    // data with no spinner. The calls do not feed back into this effect's
    // own dependency array, so — unlike the cascading-render case this rule
    // exists to catch — there is no re-render loop here.
    files: ["src/hooks/useAsync.ts"],
    rules: {
      "react-hooks/set-state-in-effect": "off",
    },
  },
];

export default eslintConfig;
