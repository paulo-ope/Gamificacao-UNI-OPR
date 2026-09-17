const backendUrl = process.env.INTERNAL_API_URL ?? "http://localhost:8000";

// A chave `webpack` só entra no config em dev: o Next 16 usa Turbopack por padrão em `next build`
// (produção) e recusa o build se achar uma config `webpack` presente, mesmo que a função nunca
// aplique nada fora do modo dev - por isso ela precisa estar ausente do objeto, não só condicional
// por dentro da função.
const isDev = process.env.NODE_ENV !== "production";

/** @type {import('next').NextConfig} */
const nextConfig = {
  // Gera .next/standalone (server + só as deps de node_modules realmente usadas em runtime,
  // via tracing de import) - o Dockerfile passa a copiar isso em vez do node_modules inteiro,
  // cortando o tamanho da imagem final (pedido do usuário em 2026-08-21, deploy mais leve na VM).
  output: "standalone",
  reactStrictMode: true,
  devIndicators: false,
  allowedDevOrigins: ["127.0.0.1", "192.168.2.100", "192.168.137.1"],
  // Recalcular um mes inteiro (10k+ O.S) passa de 30s - o proxy de /api/:path* (rewrites abaixo)
  // usava o timeout padrao do Next (~30s) e derrubava a conexao com "socket hang up" antes do
  // backend terminar, embora o calculo em si tivesse sucesso (commit ja tinha acontecido).
  experimental: {
    proxyTimeout: 120_000,
  },
  ...(isDev
    ? {
        // Achado real (2026-07-29): o bind mount do OneDrive é ~1000x mais lento que filesystem
        // nativo. WATCHPACK_POLLING=true por si só ativa o intervalo padrão do watchpack, que é
        // curto demais pra esse disco - martelava I/O constante e travava a aplicação por vários
        // segundos quando coincidia com uma sincronização do OneDrive. poll:2000 +
        // aggregateTimeout maior reduz a frequência de varredura sem atrapalhar o fluxo normal de
        // "salvar e ver a mudança".
        webpack: (config) => {
          config.watchOptions = { poll: 2000, aggregateTimeout: 500, ignored: /node_modules/ };
          return config;
        },
      }
    : {}),
  // Headers de segurança defensivos - achado da auditoria de 2026-09-14: nenhum header desse tipo
  // existia, nem aqui nem no FastAPI. Implementados só aqui (não duplicados no backend) porque o
  // navegador só fala diretamente com o Next.js: as rotas de API também chegam ao cliente através
  // do proxy `/api/:path*` abaixo, então um único `headers()` cobrindo `/:path*` já protege tanto
  // as páginas quanto as respostas de API que o navegador recebe.
  //
  // Sem CSP de propósito (pedido explícito): a tela carrega ECharts, Radix, fontes e outros
  // recursos que precisariam de um levantamento cuidadoso de origens antes de travar uma política -
  // uma CSP errada quebra a tela em produção de um jeito que só aparece depois do deploy. Fica
  // registrado como melhoria futura, não implementada às cegas aqui.
  //
  // `X-Frame-Options: SAMEORIGIN` (não `DENY`): há evidência de que a tela já rodou dentro de um
  // iframe em algum ambiente (ver hooks/use-prompt.tsx, achado de 2026-08-29 sobre `window.prompt`
  // em iframe) - sem confirmar se é um embed cross-origin legítimo, `DENY` arriscava quebrar esse
  // uso. `SAMEORIGIN` ainda bloqueia o ataque real de clickjacking (um site DE FORA enquadrando
  // esta aplicação).
  async headers() {
    return [
      {
        source: "/:path*",
        headers: [
          { key: "X-Content-Type-Options", value: "nosniff" },
          { key: "X-Frame-Options", value: "SAMEORIGIN" },
          { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
          // Desliga por padrão recursos de navegador que a aplicação não usa - a Geolocation API
          // (usada pelo UNI Localiza) continua liberada, mas só para a própria origem.
          { key: "Permissions-Policy", value: "geolocation=(self), camera=(), microphone=(), payment=()" },
          // HSTS só tem efeito quando o navegador já viu a resposta por HTTPS - inofensivo em
          // desenvolvimento (http://localhost, onde o navegador ignora o header) e reforça produção
          // (VM atrás de proxy reverso com TLS, ver FRONTEND_URL em .env.example).
          { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
        ],
      },
    ];
  },
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`
      },
      // O conector MCP remoto (backend/app/modules/mcp_connector) fica montado sob /api/mcp, mas
      // a RFC 9728 (e a função build_resource_metadata_url do SDK do MCP) sempre calcula a URL de
      // metadados do recurso protegido colocando /.well-known/oauth-protected-resource logo após
      // a raiz do domínio, ignorando esse prefixo - achado real: sem este redirect, o Claude segue
      // a URL do cabeçalho WWW-Authenticate, cai na raiz (que o Next.js serve, não o backend),
      // toma 404 e desiste silenciosamente de completar a conexão OAuth.
      {
        source: "/.well-known/oauth-protected-resource/:path*",
        destination: `${backendUrl}/api/mcp/.well-known/oauth-protected-resource/:path*`
      },
      // Mesmo problema, segunda rota: a RFC 8414 manda o cliente descobrir os metadados do
      // authorization server inserindo /.well-known/oauth-authorization-server ANTES do path do
      // issuer (aqui, /api/mcp) - ou seja, na raiz do domínio. O SDK do MCP, porém, registra essa
      // rota sem o sufixo do path (só /.well-known/oauth-authorization-server dentro do sub-app),
      // então o alvo do redirect não repete :path* no destino.
      {
        source: "/.well-known/oauth-authorization-server/:path*",
        destination: `${backendUrl}/api/mcp/.well-known/oauth-authorization-server`
      }
    ];
  }
};

export default nextConfig;
