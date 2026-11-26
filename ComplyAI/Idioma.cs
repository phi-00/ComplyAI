using System;
using System.Collections.Generic;
using System.IO;
using System.Runtime.CompilerServices;
using System.Windows.Forms;

namespace ComplyAI
{
    // Modo de língua da aplicação (Português / English).
    // - Textos fixos da aplicação (menus, separadores, cabeçalhos, avisos): traduzidos aqui, a partir do texto em
    //   português que está no Designer / no código (T("...")).
    // - Conteúdo (requisitos, análises, ITs, chat): vem já traduzido do servidor (?lang=pt|en, ver server.py e
    //   LocalLLM/complyai/i18n.py); a tradução foi feita pelo modelo local quando o documento foi processado.
    // A escolha fica guardada em %LOCALAPPDATA%\ComplyAI\idioma.txt e vale para todas as janelas e projetos.
    public static class Idioma
    {
        private static readonly string Ficheiro = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.LocalApplicationData), "ComplyAI", "idioma.txt");

        private static string atual = Ler();

        // "pt" ou "en"
        public static string Atual { get { return atual; } }
        public static bool Ingles { get { return atual == "en"; } }

        // Avisa as janelas abertas para se traduzirem e recarregarem o conteúdo
        public static event EventHandler Mudou;

        public static void Definir(string lingua)
        {
            lingua = lingua == "en" ? "en" : "pt";
            if (lingua == atual)
                return;
            atual = lingua;
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(Ficheiro));
                File.WriteAllText(Ficheiro, lingua);
            }
            catch { }
            Mudou?.Invoke(null, EventArgs.Empty);
        }

        private static string Ler()
        {
            try
            {
                if (File.Exists(Ficheiro) && File.ReadAllText(Ficheiro).Trim() == "en")
                    return "en";
            }
            catch { }
            return "pt";
        }

        // Parâmetro para os pedidos ao servidor
        public static string Query { get { return "lang=" + atual; } }

        public static string ComLang(string url)
        {
            return url + (url.Contains("?") ? "&" : "?") + Query;
        }

        // Texto fixo: em português tal como está; em inglês a tradução (se não existir, fica o português)
        public static string T(string pt)
        {
            if (pt == null || !Ingles)
                return pt;
            string en;
            return EN.TryGetValue(pt, out en) ? en : pt;
        }

        // Valores que o servidor envia sempre em inglês no JSON da matriz (estados, gravidades, tipos):
        // em modo português usa-se o mapa "value_labels" que o servidor envia com a matriz
        public static string Valor(string en, IDictionary<string, string> etiquetas)
        {
            if (string.IsNullOrEmpty(en) || Ingles || etiquetas == null)
                return en;
            string pt;
            return etiquetas.TryGetValue(en, out pt) ? pt : en;
        }

        // Guarda o texto original (português) de cada controlo da primeira vez que é traduzido,
        // para se poder voltar a português sem perder nada
        private static readonly ConditionalWeakTable<object, string> Originais =
            new ConditionalWeakTable<object, string>();

        private static string Original(object componente, string texto)
        {
            string guardado;
            if (Originais.TryGetValue(componente, out guardado))
                return guardado;
            Originais.Add(componente, texto ?? "");
            return texto ?? "";
        }

        // Traduz os textos fixos de uma janela: controlos, separadores, colunas das grelhas e menus
        public static void Aplicar(Control raiz)
        {
            foreach (Control controlo in raiz.Controls)
            {
                if (controlo is TextBoxBase || controlo is ListBox || controlo is ComboBox)
                    continue; // texto do utilizador / dados
                if (!string.IsNullOrEmpty(controlo.Text) || Originais.TryGetValue(controlo, out _))
                    controlo.Text = T(Original(controlo, controlo.Text));

                var grelha = controlo as DataGridView;
                if (grelha != null)
                    foreach (DataGridViewColumn coluna in grelha.Columns)
                        coluna.HeaderText = T(Original(coluna, coluna.HeaderText));

                var menu = controlo as ToolStrip;
                if (menu != null)
                    AplicarMenu(menu.Items);

                if (controlo.HasChildren)
                    Aplicar(controlo);
            }
        }

        private static void AplicarMenu(ToolStripItemCollection itens)
        {
            foreach (ToolStripItem item in itens)
            {
                if (item.Tag as string == "idioma")
                    continue; // os nomes das línguas ficam sempre na própria língua
                item.Text = T(Original(item, item.Text));
                var submenu = item as ToolStripDropDownItem;
                if (submenu != null && submenu.HasDropDownItems)
                    AplicarMenu(submenu.DropDownItems);
            }
        }

        private static readonly Dictionary<string, string> EN = new Dictionary<string, string>
        {
            // Form1: menus
            { "Projects", "Projects" },
            { "Abrir Outro Projeto", "Open another project" },
            { "Importar PDF de requisitos", "Import requirements PDF" },
            { "Descarregar matriz", "Download matrix" },
            { "Enviar alterações", "Send changes" },
            { "Atualizar", "Refresh" },
            { "Sair", "Exit" },
            { "Menu", "Menu" },
            { "Abrir chatbot", "Open chatbot" },
            { "Solicitar atualização", "Request update" },
            { "Configurações", "Settings" },
            { "Idioma", "Language" },
            // Form1: separadores, títulos, colunas
            { "Chatbot", "Chatbot" },
            { "Enviar", "Send" },
            { "Assistente visual para dúvidas sobre o projeto.", "Visual assistant for questions about the project." },
            { "Chatbot ComplyAI", "ComplyAI chatbot" },
            { "Matrix", "Matrix" },
            { "Secção", "Section" },
            { "Página", "Page" },
            { "Processo LEONI", "LEONI process" },
            { "Normas", "Standards" },
            { "Código", "Code" },
            { "Descrição", "Description" },
            { "Requisitos", "Requirements" },
            { "Nº do requisito", "Requirement no." },
            { "Instruções", "Instructions" },
            { "ID do requisito", "Requirement ID" },
            { "Conflitos", "Conflicts" },
            { "ITs avaliadas", "ITs assessed" },
            { "Estado", "Status" },
            { "Alterações", "Changes" },
            { "Enviar resolução", "Send resolution" },
            { "Cliente:", "Customer:" },
            { "Titulo:", "Title:" },
            // Form1: textos do código
            { "Cliente: ", "Customer: " },
            { "Titulo: ", "Title: " },
            { "Titulo: Sem documentos processados", "Title: No processed documents" },
            { "Titulo: Erro ao obter documentos", "Title: Error getting documents" },
            { "Não foi possível obter os documentos do projeto:\n\n", "Could not get the project's documents:\n\n" },
            { "Erro de comunicação", "Communication error" },
            { "Selecionar PDF de requisitos", "Select requirements PDF" },
            { "O PDF foi processado e a matriz foi atualizada.", "The PDF was processed and the matrix was updated." },
            { "Processamento concluído", "Processing finished" },
            { "Não foi possível processar o PDF:\n\n", "Could not process the PDF:\n\n" },
            { "Erro", "Error" },
            { "Não foi possível consultar o estado do processamento.", "Could not check the processing status." },
            { "Falha desconhecida", "Unknown failure" },
            { "O processamento excedeu o tempo máximo.", "Processing took longer than the maximum time." },
            { "Você", "You" },
            { "A escrever.", "Writing." },
            { "A escrever..", "Writing.." },
            { "A escrever...", "Writing..." },
            { "Não foi possível responder: ", "Could not answer: " },
            { "Não existe um documento ativo para exportar.", "There is no active document to export." },
            { "Matriz", "Matrix" },
            { "Guardar matriz", "Save matrix" },
            { "Matriz guardada com sucesso.", "Matrix saved." },
            { "Exportação", "Export" },
            { "Não foi possível descarregar a matriz:\n\n", "Could not download the matrix:\n\n" },
            { "Não foi possível guardar a alteração:\n\n", "Could not save the change:\n\n" },
            { "Confirmar requisito", "Confirm requirement" },
            { "Aprovar", "Approve" },
            { "Rejeitar", "Reject" },
            { "Pendente", "Pending" },
            { "Não existe um documento ativo.", "There is no active document." },
            { "Resolução de conflitos", "Conflict resolution" },
            { "Escreva pelo menos uma resolução na coluna Alterações.", "Write at least one resolution in the Changes column." },
            { " resolução(ões) enviada(s) ao servidor.", " resolution(s) sent to the server." },
            { "Não foi possível enviar as resoluções:\n\n", "Could not send the resolutions:\n\n" },
            { "Não existem alterações pendentes.", "There are no pending changes." },
            { "Alterações enviadas ao servidor.", "Changes sent to the server." },
            { "Não foi possível enviar as alterações:\n\n", "Could not send the changes:\n\n" },
            // FormInicio
            { "Ver lista de projetos", "Show project list" },
            { "A verificar ligação ao servidor...", "Checking the server connection..." },
            { "Projetos disponíveis", "Available projects" },
            { "Servidor ligado", "Server connected" },
            { "Servidor indisponível", "Server unavailable" },
            { "Ligação ao servidor perdida!", "Server connection lost!" },
            { "Sem ligação ao servidor", "No server connection" },
            { "Não existem projetos disponíveis.", "No projects available." },
            { " projeto(s) encontrado(s).", " project(s) found." },
            { "Erro ao obter projetos.", "Error getting projects." },
            { "Não foi possível pesquisar os projetos automaticamente:\n\n", "Could not look up the projects automatically:\n\n" },
            { "A obter projetos...", "Getting projects..." },
            { "Erro ao obter projetos:\n\n", "Error getting projects:\n\n" },
            { "Erro de ligação ao servidor.", "Server connection error." },
            { "A descarregar projeto...", "Downloading project..." },
            { "A extrair documentos...", "Extracting documents..." },
            { "A comunicar com o servidor...", "Contacting the server..." },
            { "Não foi possível carregar o projeto:\n\n", "Could not load the project:\n\n" },
            { "Erro ao carregar projeto.", "Error loading project." },
        };
    }
}
