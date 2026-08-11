import type { Metadata } from "next";

// Página pública, sem autenticação - serve como Política de Privacidade de uma Ação
// personalizada de GPT/conector de IA para o UNI Analítico. Não importa nada do fluxo de login
// (WorkspaceHome/WorkspaceLogin) de propósito: precisa carregar em HTTP 200 sem sessão, cookie,
// token ou redirecionamento, inclusive para validadores automatizados de terceiros.

export const metadata: Metadata = {
  title: "Política de Privacidade | UNI Analítico",
  description:
    "Explica como o UNI Analítico trata informações durante consultas realizadas por usuários autorizados, inclusive por meio de integrações com assistentes de inteligência artificial.",
};

const LAST_UPDATED = "11 de agosto de 2026";

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24">
      <h2 className="text-xl font-semibold text-slate-950">{title}</h2>
      <div className="mt-3 grid gap-3 text-sm leading-relaxed text-slate-700">{children}</div>
    </section>
  );
}

export default function PoliticaDePrivacidadePage() {
  return (
    <div className="min-h-screen bg-slate-50">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center gap-3 px-4 py-5 sm:px-6">
          <img src="/brand/uni-logo.png" alt="UNI Internet" className="h-8 w-auto" />
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.2em] text-blue-600">UNI Analítico</p>
            <p className="text-sm text-slate-500">Política de Privacidade</p>
          </div>
        </div>
      </header>

      <main className="mx-auto max-w-3xl px-4 py-10 sm:px-6">
        <h1 className="text-2xl font-semibold text-slate-950 sm:text-3xl">Política de Privacidade — UNI Analítico</h1>
        <p className="mt-2 text-sm text-slate-500">Última atualização: {LAST_UPDATED}</p>

        <div className="mt-8 grid gap-10">
          <Section id="sobre" title="1. Sobre esta política">
            <p>
              Esta Política de Privacidade descreve como o UNI Analítico trata informações durante consultas
              realizadas por usuários autorizados, inclusive por meio de integrações com assistentes de
              inteligência artificial (como Ações personalizadas de GPTs e conectores compatíveis com o Model
              Context Protocol). Ela se aplica a todas as formas de acesso às ferramentas de consulta do UNI
              Analítico, sejam elas feitas diretamente pela interface do sistema ou por uma integração de IA
              autorizada.
            </p>
          </Section>

          <Section id="finalidade" title="2. Finalidade do sistema">
            <p>
              O UNI Analítico é uma ferramenta de apoio à análise operacional, utilizada por colaboradores e
              gestores autorizados da UNI Internet para consultar e consolidar informações relacionadas a
              ordens de serviço, produtividade, atendimento, cumprimento de SLA, backlog, equipes, setores e
              regionais de atuação.
            </p>
          </Section>

          <Section id="dados-tratados" title="3. Dados que podem ser tratados">
            <p>Conforme o funcionamento real da aplicação, as consultas podem envolver:</p>
            <ul className="ml-5 list-disc grid gap-1.5">
              <li>identificação e número da ordem de serviço;</li>
              <li>assunto, setor, status e datas da ordem;</li>
              <li>regional, cidade, bairro e endereço de atendimento, quando disponíveis;</li>
              <li>latitude e longitude do local de atendimento, quando disponíveis;</li>
              <li>técnico ou equipe responsável pelo atendimento;</li>
              <li>prazos, indicadores de SLA e informações de execução;</li>
              <li>relatos e diagnósticos técnicos registrados na ordem de serviço;</li>
              <li>outros dados operacionais estritamente necessários para responder à consulta solicitada.</li>
            </ul>
            <p>
              O UNI Analítico utiliza somente os dados necessários para atender à finalidade de cada consulta -
              uma pergunta sobre volume de chamados por regional, por exemplo, não precisa (e não deve) trazer
              dado de identificação de cliente para ser respondida.
            </p>
          </Section>

          <Section id="uso-dos-dados" title="4. Como os dados são utilizados">
            <p>Os dados consultados podem ser usados para:</p>
            <ul className="ml-5 list-disc grid gap-1.5">
              <li>gerar relatórios e indicadores operacionais;</li>
              <li>identificar concentrações de chamados e possíveis problemas coletivos por área ou bairro;</li>
              <li>acompanhar produtividade, capacidade e cumprimento de metas e SLA por equipe;</li>
              <li>localizar ordens de serviço pendentes ou próximas do vencimento de prazo;</li>
              <li>apoiar decisões operacionais da UNI Internet;</li>
              <li>responder às solicitações realizadas por usuários autorizados, inclusive via integração de IA.</li>
            </ul>
          </Section>

          <Section id="integracao-chatgpt" title="5. Integração com o ChatGPT e outros assistentes de IA">
            <p>
              O UNI Analítico pode disponibilizar uma integração por API (incluindo uma Ação personalizada de
              GPT e um conector compatível com o Model Context Protocol) para uso por assistentes de
              inteligência artificial em nome de um usuário autorizado. Quando esse usuário realiza uma
              consulta, apenas os dados necessários para executar aquela solicitação específica são enviados
              pela API ao serviço de inteligência artificial utilizado - a integração não transmite bases de
              dados completas nem informações fora do escopo da pergunta feita.
            </p>
            <p>
              O uso do ChatGPT (ou de qualquer outro assistente de IA integrado) também está sujeito aos termos
              e à política de privacidade do respectivo provedor. No caso do ChatGPT, aplica-se a Política de
              Privacidade da OpenAI, disponível em{" "}
              <a
                href="https://openai.com/policies/privacy-policy/"
                target="_blank"
                rel="noopener noreferrer"
                className="font-medium text-blue-600 underline underline-offset-2"
              >
                https://openai.com/policies/privacy-policy/
              </a>
              . O tratamento realizado pela OpenAI sobre os dados enviados durante uma consulta - incluindo se e
              por quanto tempo eles são retidos - depende da configuração da conta e do produto utilizados por
              quem faz a consulta, e não é controlado pelo UNI Analítico.
            </p>
          </Section>

          <Section id="compartilhamento" title="6. Compartilhamento de informações">
            <p>
              Os dados tratados pelo UNI Analítico podem ser processados por fornecedores tecnológicos
              necessários ao funcionamento da aplicação (por exemplo, provedores de hospedagem, infraestrutura
              e, quando a integração de IA é utilizada, o respectivo provedor do assistente), sempre de acordo
              com a finalidade operacional descrita nesta política e com as medidas de segurança aplicáveis.
            </p>
            <p>Os dados tratados pelo UNI Analítico não são comercializados.</p>
          </Section>

          <Section id="armazenamento" title="7. Armazenamento e retenção">
            <p>
              O conteúdo das consultas (parâmetros enviados e resultados retornados) não é armazenado pelo UNI
              Analítico como um histórico de perguntas e respostas. O sistema mantém apenas metadados técnicos
              de autenticação necessários à operação e à segurança do acesso - por exemplo, a data do último
              uso de uma credencial de integração -, além dos registros padrão de acesso ao servidor (como
              data, hora e rota chamada), mantidos pelo tempo necessário para fins de operação, auditoria e
              segurança da infraestrutura.
            </p>
          </Section>

          <Section id="seguranca" title="8. Segurança e controle de acesso">
            <p>
              O UNI Analítico adota medidas administrativas e técnicas para limitar o acesso às informações,
              proteger credenciais, controlar usuários e reduzir riscos de acesso, alteração, divulgação ou
              destruição indevida de dados - incluindo autenticação individual, permissões específicas por
              usuário e, no caso de integrações de IA, um fluxo de autorização em que a própria pessoa usuária
              precisa entrar com sua conta e aprovar explicitamente o acesso antes de qualquer consulta ser
              realizada em seu nome.
            </p>
            <p>
              Nenhum sistema é absolutamente livre de risco; a UNI Internet trabalha continuamente para manter
              essas medidas atualizadas, mas não é possível garantir segurança absoluta.
            </p>
          </Section>

          <Section id="direitos" title="9. Direitos dos titulares">
            <p>
              Nos termos da Lei Geral de Proteção de Dados (LGPD - Lei nº 13.709/2018), quando aplicável aos
              dados tratados, os titulares podem solicitar, entre outros direitos previstos em lei:
            </p>
            <ul className="ml-5 list-disc grid gap-1.5">
              <li>confirmação da existência de tratamento;</li>
              <li>acesso aos dados;</li>
              <li>correção de dados incompletos, inexatos ou desatualizados;</li>
              <li>anonimização, bloqueio ou eliminação de dados desnecessários ou excessivos;</li>
              <li>informação sobre as entidades com as quais os dados foram compartilhados;</li>
              <li>demais direitos previstos na legislação aplicável.</li>
            </ul>
          </Section>

          <Section id="contato" title="10. Contato">
            <ul className="ml-0 grid gap-1.5 list-none">
              <li>
                <span className="font-medium text-slate-900">Empresa responsável:</span>{" "}
                <span>UNI SERVIÇOS DE TECNOLOGIA DA INFORMAÇÃO LTDA</span>
              </li>
              <li>
                <span className="font-medium text-slate-900">CNPJ:</span> <span>49.232.014/0001-20</span>
              </li>
              <li>
                <span className="font-medium text-slate-900">E-mail de privacidade:</span>{" "}
                <a href="mailto:operacional@souuni.com" className="font-medium text-blue-600 underline underline-offset-2">
                  operacional@souuni.com
                </a>
              </li>
            </ul>
          </Section>

          <Section id="alteracoes" title="11. Alterações desta política">
            <p>
              Esta política poderá ser atualizada para refletir mudanças legais, operacionais ou tecnológicas.
              A versão mais recente permanecerá sempre disponível nesta mesma URL.
            </p>
          </Section>

          <Section id="ultima-atualizacao" title="12. Última atualização">
            <p>Esta versão da política foi publicada em {LAST_UPDATED}.</p>
          </Section>
        </div>
      </main>

      <footer className="border-t border-slate-200 bg-white py-6">
        <div className="mx-auto max-w-3xl px-4 text-xs text-slate-500 sm:px-6">
          <p>Última atualização: {LAST_UPDATED}</p>
          <p className="mt-1">UNI Analítico — UNI Internet.</p>
        </div>
      </footer>
    </div>
  );
}
