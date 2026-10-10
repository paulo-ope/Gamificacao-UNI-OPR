import type { Config } from "tailwindcss";

const config: Config = {
  darkMode: ["class"],
  content: [
    "./app/**/*.{ts,tsx}",
    "./components/**/*.{ts,tsx}",
    "./lib/**/*.{ts,tsx}"
  ],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"]
      },
      colors: {
        // Manual da marca UNI Internet 2026 (mesmos valores das variáveis --uni-* em globals.css).
        // Acentos de marca usam estas cores; emerald/amber/red continuam como cores SEMÂNTICAS
        // (sucesso/alerta/erro), que o manual não substitui.
        uni: {
          royal: "#2d5fff",
          turquoise: "#27d9bf",
          impact: "#0028f3",
          electric: "#000ecc",
          midnight: "#010c8b",
          cyan: "#02fffa",
          rich: "#151f27",
          // Tinta e apoio da tela de acesso (components/workspace/workspace-login.css): o item ativo
          // da barra lateral usa este azul-névoa de fundo.
          ink: "#152747",
          mist: "#edf2ff"
        },
        // Escala de neutros alinhada à tela de acesso (tinta azul-marinho em vez do cinza frio padrão
        // do Tailwind): 900 = #152747 (texto), 200 = #dfe7f2 (bordas), 50 = #f7f9fc (fundo). Remapear
        // aqui troca ~4.000 usos de `slate-*` de uma vez, sem editar tela por tela. O 500 é um pouco
        // mais escuro que o #6a7c97 do login (#5f7391) para manter contraste AA (>= 4,5:1) no texto
        // secundário sobre branco.
        slate: {
          50: "#f7f9fc",
          100: "#eef2f8",
          200: "#dfe7f2",
          300: "#c4d3e6",
          400: "#97accf",
          500: "#5f7391",
          600: "#4a5d7a",
          700: "#364866",
          800: "#1f3052",
          900: "#152747",
          950: "#0d1b36"
        },
        border: "hsl(var(--border))",
        input: "hsl(var(--input))",
        ring: "hsl(var(--ring))",
        background: "hsl(var(--background))",
        foreground: "hsl(var(--foreground))",
        primary: {
          DEFAULT: "hsl(var(--primary))",
          foreground: "hsl(var(--primary-foreground))"
        },
        secondary: {
          DEFAULT: "hsl(var(--secondary))",
          foreground: "hsl(var(--secondary-foreground))"
        },
        muted: {
          DEFAULT: "hsl(var(--muted))",
          foreground: "hsl(var(--muted-foreground))"
        },
        accent: {
          DEFAULT: "hsl(var(--accent))",
          foreground: "hsl(var(--accent-foreground))"
        },
        destructive: {
          DEFAULT: "hsl(var(--destructive))",
          foreground: "hsl(var(--destructive-foreground))"
        },
        card: {
          DEFAULT: "hsl(var(--card))",
          foreground: "hsl(var(--card-foreground))"
        },
        popover: {
          DEFAULT: "hsl(var(--popover))",
          foreground: "hsl(var(--popover-foreground))"
        }
      },
      borderRadius: {
        lg: "12px",
        md: "var(--radius-control)",
        sm: "6px",
        panel: "var(--radius-panel)"
      },
      boxShadow: {
        panel: "var(--shadow-panel)",
        floating: "var(--shadow-floating)"
      }
    }
  },
  plugins: [require("tailwindcss-animate")]
};

export default config;
