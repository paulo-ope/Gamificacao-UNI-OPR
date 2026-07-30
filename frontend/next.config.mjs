const backendUrl = process.env.INTERNAL_API_URL ?? "http://localhost:8000";

// A chave `webpack` só entra no config em dev: o Next 16 usa Turbopack por padrão em `next build`
// (produção) e recusa o build se achar uma config `webpack` presente, mesmo que a função nunca
// aplique nada fora do modo dev - por isso ela precisa estar ausente do objeto, não só condicional
// por dentro da função.
const isDev = process.env.NODE_ENV !== "production";

/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  devIndicators: false,
  allowedDevOrigins: ["127.0.0.1", "192.168.2.100", "192.168.137.1"],
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
  async rewrites() {
    return [
      {
        source: "/api/:path*",
        destination: `${backendUrl}/api/:path*`
      }
    ];
  }
};

export default nextConfig;
