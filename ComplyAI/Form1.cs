using System;
using System.Drawing;
using System.IO;
using System.Net.Http;
using System.Runtime.InteropServices;
using System.Collections.Generic;
using System.Text.Json;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace ComplyAI
{
    public partial class Form1 : Form
    {
        private const string SERVER_URL = "http://localhost:9000";
        private static readonly HttpClient httpClient = new HttpClient()
        {
            Timeout = TimeSpan.FromMinutes(10)
        };

        private const int WmNclButtonDown = 0x00A1;
        private const int HtCaption = 0x2;
        private readonly string projetoNome;
        private int? activeDocumentId;
        private readonly Dictionary<int, string> alteracoesRequisitos =
            new Dictionary<int, string>();
        private readonly Dictionary<int, string> alteracoesInstrucoes =
            new Dictionary<int, string>();
        private readonly List<Dictionary<string, string>> chatHistory =
            new List<Dictionary<string, string>>();

        [DllImport("user32.dll")]
        private static extern bool ReleaseCapture();

        [DllImport("user32.dll")]
        private static extern IntPtr SendMessage(IntPtr hWnd, int msg, int wParam, int lParam);

        public string ProjetoPath { get; private set; }

        public Form1()
            : this(string.Empty)
        {
        }

        public Form1(string projetoPath)
        {
            InitializeComponent();

            ProjetoPath = projetoPath;
            projetoNome = new DirectoryInfo(projetoPath.TrimEnd(Path.DirectorySeparatorChar)).Name;
            Text = "ComplyAI";
            TitleBar.MouseDown += TitleBar_MouseDown;
            menuStrip1.MouseDown += TitleBar_MouseDown;
            button1.BringToFront();
            button2.BringToFront();
            button3.BringToFront();
            sairToolStripMenuItem.Click += sairToolStripMenuItem_Click;
            abrirOutroProjetoToolStripMenuItem.Click += abrirOutroProjetoToolStripMenuItem_Click;
            pedirCookiesToolStripMenuItem.Click += pedirCookiesToolStripMenuItem_Click;
            importarPdfToolStripMenuItem.Click += importarPdfToolStripMenuItem_Click;
            atualizarToolStripMenuItem.Click += atualizarToolStripMenuItem_Click;
            descarregarMatrizToolStripMenuItem.Click += descarregarMatrizToolStripMenuItem_Click;
            enviarAlteracoesToolStripMenuItem.Click += enviarAlteracoesToolStripMenuItem_Click;
            chatbotToolStripMenuItem.Click += chatbotToolStripMenuItem_Click;
            chatEntrada.KeyDown += chatEntrada_KeyDown;
            enviarResolucaoConflitos.Click += enviarResolucaoConflitos_Click;
            requisitosGrid.CellDoubleClick += requisitosGrid_CellDoubleClick;
            dataGridView1.ReadOnly = false;
            foreach (DataGridViewColumn column in dataGridView1.Columns)
                column.ReadOnly = false;
            dataGridView1.CellEndEdit += dataGridView1_CellEndEdit;
            requisitosGrid.CellEndEdit += requisitosGrid_CellEndEdit;
            instrucoesGrid.CellEndEdit += instrucoesGrid_CellEndEdit;
            Load += Form1_Load;
        }

        private async void atualizarToolStripMenuItem_Click(object sender, EventArgs e)
        {
            await ObterDocumentosAtivos();
        }

        private async void Form1_Load(object sender, EventArgs e)
        {
            await ObterDocumentosAtivos();
        }

        private async Task ObterDocumentosAtivos()
        {
            try
            {
                string url = SERVER_URL + "/projects/" +
                             Uri.EscapeDataString(projetoNome) + "/documents";
                using (var response = await httpClient.GetAsync(url))
                {
                    if (!response.IsSuccessStatusCode)
                    {
                        label1.Text = "Cliente: " + projetoNome;
                        label2.Text = "Titulo: Sem documentos processados";
                        return;
                    }

                    string json = await response.Content.ReadAsStringAsync();
                    using (var document = JsonDocument.Parse(json))
                    {
                        JsonElement root = document.RootElement;
                        JsonElement documentsElement;
                        if (!root.TryGetProperty("documents", out documentsElement) ||
                            documentsElement.GetArrayLength() == 0)
                        {
                            label1.Text = "Cliente: " + projetoNome;
                            label2.Text = "Titulo: Sem documentos processados";
                            activeDocumentId = null;
                            return;
                        }

                        JsonElement active;
                        if (root.TryGetProperty("active_document_id", out JsonElement activeIdElement) &&
                            activeIdElement.ValueKind == JsonValueKind.Number)
                        {
                            activeDocumentId = activeIdElement.GetInt32();
                            active = default(JsonElement);
                            foreach (JsonElement documentRow in documentsElement.EnumerateArray())
                            {
                                if (documentRow.GetProperty("id").GetInt32() == activeDocumentId.Value)
                                {
                                    active = documentRow;
                                    break;
                                }
                            }
                            if (active.ValueKind == JsonValueKind.Undefined)
                            {
                                active = documentsElement[0];
                            }
                        }
                        else
                        {
                            active = documentsElement[0];
                            activeDocumentId = active.GetProperty("id").GetInt32();
                        }

                        string titulo = active.TryGetProperty("title", out JsonElement titleElement)
                            ? titleElement.GetString()
                            : active.GetProperty("source_file").GetString();
                        label1.Text = "Cliente: " + projetoNome;
                        label2.Text = "Titulo: " + (titulo ?? "");

                        await CarregarMatrizJson(activeDocumentId.Value);
                    }
                }
            }
            catch (Exception ex)
            {
                label1.Text = "Cliente: " + projetoNome;
                label2.Text = "Titulo: Erro ao obter documentos";
                MessageBox.Show(
                    "Não foi possível obter os documentos do projeto:\n\n" + ex.Message,
                    "Erro de comunicação",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }

        private async void importarPdfToolStripMenuItem_Click(object sender, EventArgs e)
        {
            using (var dialog = new OpenFileDialog())
            {
                dialog.Title = "Selecionar PDF de requisitos";
                dialog.Filter = "PDF (*.pdf)|*.pdf";
                dialog.Multiselect = false;
                if (dialog.ShowDialog(this) != DialogResult.OK)
                    return;

                await EnviarPdfRequisitos(dialog.FileName);
            }
        }

        private async Task EnviarPdfRequisitos(string pdfPath)
        {
            try
            {
                Cursor = Cursors.WaitCursor;
                string url = SERVER_URL + "/files/" +
                             Uri.EscapeDataString(projetoNome) + "/requirements_pdf";

                using (var content = new MultipartFormDataContent())
                using (var fileContent = new StreamContent(File.OpenRead(pdfPath)))
                {
                    fileContent.Headers.ContentType =
                        new System.Net.Http.Headers.MediaTypeHeaderValue("application/pdf");
                    content.Add(fileContent, "file", Path.GetFileName(pdfPath));

                    using (var response = await httpClient.PostAsync(url, content))
                    {
                        string responseJson = await response.Content.ReadAsStringAsync();
                        if (!response.IsSuccessStatusCode)
                            throw new InvalidOperationException(responseJson);

                        using (var result = JsonDocument.Parse(responseJson))
                        {
                            string jobId = result.RootElement.GetProperty("job_id").GetString();
                            await AguardarProcessamento(jobId);
                        }
                    }
                }

                await ObterDocumentosAtivos();
                MessageBox.Show(
                    "O PDF foi processado e a matriz foi atualizada.",
                    "Processamento concluído",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Não foi possível processar o PDF:\n\n" + ex.Message,
                    "Erro",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
            finally
            {
                Cursor = Cursors.Default;
            }
        }

        private async Task AguardarProcessamento(string jobId)
        {
            for (int attempt = 0; attempt < 720; attempt++)
            {
                using (var response = await httpClient.GetAsync(
                    SERVER_URL + "/jobs/" + Uri.EscapeDataString(jobId)))
                {
                    if (!response.IsSuccessStatusCode)
                        throw new InvalidOperationException(
                            "Não foi possível consultar o estado do processamento.");

                    string json = await response.Content.ReadAsStringAsync();
                    using (var result = JsonDocument.Parse(json))
                    {
                        JsonElement root = result.RootElement;
                        string status = root.GetProperty("status").GetString();
                        int progress = root.TryGetProperty("progress", out JsonElement progressElement)
                            ? progressElement.GetInt32()
                            : 0;

                        if (status == "completed")
                        {
                            activeDocumentId = root.GetProperty("doc_id").GetInt32();
                            return;
                        }
                        if (status == "failed")
                        {
                            string error = root.TryGetProperty("error", out JsonElement errorElement)
                                ? errorElement.GetString()
                                : "Falha desconhecida";
                            throw new InvalidOperationException(error);
                        }
                    }
                }
                await Task.Delay(5000);
            }

            throw new TimeoutException("O processamento excedeu o tempo máximo.");
        }

        private async Task CarregarMatrizJson(int docId)
        {
            string url = SERVER_URL + "/files/" +
                         Uri.EscapeDataString(projetoNome) + "/matrix/" +
                         docId + "?format=json";

            using (var response = await httpClient.GetAsync(url))
            {
                if (!response.IsSuccessStatusCode)
                {
                    return;
                }

                string json = await response.Content.ReadAsStringAsync();
                using (var document = JsonDocument.Parse(json))
                {
                    JsonElement root = document.RootElement;
                    JsonElement matrix;
                    if (!root.TryGetProperty("matrix", out matrix))
                        return;

                    PreencherMatriz(matrix);
                    PreencherRequisitos(matrix);
                    PreencherInstrucoes(matrix);
                    PreencherConflitos(matrix);
                }
            }
        }

        private void PreencherMatriz(JsonElement matrix)
        {
            dataGridView1.Rows.Clear();
            PreencherNormas(matrix);

            JsonElement rows;
            if (!matrix.TryGetProperty("Matrix", out rows) ||
                rows.ValueKind != JsonValueKind.Array)
                return;

            foreach (JsonElement row in rows.EnumerateArray())
            {
                if (row.ValueKind != JsonValueKind.Array)
                    continue;

                var values = row.EnumerateArray();
                var cells = new System.Collections.Generic.List<JsonElement>();
                cells.AddRange(values);
                if (cells.Count < 10)
                    continue;

                string conteudo = LerCelula(cells, 1);
                if (string.IsNullOrWhiteSpace(conteudo) ||
                    conteudo.Equals("Conteudo", StringComparison.OrdinalIgnoreCase) ||
                    conteudo.Equals("Conteúdo", StringComparison.OrdinalIgnoreCase) ||
                    conteudo.Equals("Secção", StringComparison.OrdinalIgnoreCase) ||
                    conteudo.Equals("Seção", StringComparison.OrdinalIgnoreCase) ||
                    conteudo.Equals("Section", StringComparison.OrdinalIgnoreCase))
                    continue;

                dataGridView1.Rows.Add(
                    conteudo,
                    LerCelula(cells, 2),
                    LerCelula(cells, 4),
                    LerCelula(cells, 6),
                    LerCelula(cells, 9));
            }
        }

        private void PreencherNormas(JsonElement matrix)
        {
            normasGrid.Rows.Clear();

            JsonElement rows;
            if (!matrix.TryGetProperty("Matrix", out rows) ||
                rows.ValueKind != JsonValueKind.Array)
                return;

            var normas = new HashSet<string>(StringComparer.OrdinalIgnoreCase);

            foreach (JsonElement row in rows.EnumerateArray())
            {
                if (row.ValueKind != JsonValueKind.Array)
                    continue;

                var values = row.EnumerateArray();
                var cells = new List<JsonElement>();
                cells.AddRange(values);

                AdicionarNormas(cells, 6, "PROC. WSD", normas);
                AdicionarNormas(cells, 9, "PROC. WPTGU", normas);
            }
        }

        private void AdicionarNormas(
            IList<JsonElement> cells,
            int columnIndex,
            string origem,
            HashSet<string> normas)
        {
            string valor = LerCelula(cells, columnIndex);
            if (string.IsNullOrWhiteSpace(valor))
                return;

            foreach (string linha in valor.Split(
                new[] { "\r\n", "\n", "\r" },
                StringSplitOptions.RemoveEmptyEntries))
            {
                string norma = linha.Trim().TrimStart('•', '-', ' ');
                if (string.IsNullOrWhiteSpace(norma))
                    continue;

                string chave = origem + "|" + norma;
                if (!normas.Add(chave))
                    continue;

                string codigo;
                string descricao;
                SepararCodigoDescricao(norma, out codigo, out descricao);
                normasGrid.Rows.Add(codigo, descricao + " (" + origem + ")");
            }
        }

        private static void SepararCodigoDescricao(
            string norma,
            out string codigo,
            out string descricao)
        {
            codigo = "";
            descricao = "";
            if (string.IsNullOrWhiteSpace(norma))
                return;

            string texto = norma.Trim();
            var correspondencia = System.Text.RegularExpressions.Regex.Match(
                texto,
                @"^(IT|WI|VA|PI|IC)\s+([\dA-Z.-]+(?:\s+A\d+)*)\s*(.*)$",
                System.Text.RegularExpressions.RegexOptions.IgnoreCase);
            if (correspondencia.Success)
            {
                codigo = (correspondencia.Groups[1].Value + " " +
                          correspondencia.Groups[2].Value).Trim();
                descricao = correspondencia.Groups[3].Value.Trim();
            }
            else
            {
                int separador = texto.IndexOf(' ');
                if (separador > 0)
                {
                    codigo = texto.Substring(0, separador).Trim();
                    descricao = texto.Substring(separador + 1).Trim();
                }
                else
                {
                    codigo = texto;
                }
            }
        }

        private static string ExtrairCodigoProcesso(string texto)
        {
            if (string.IsNullOrWhiteSpace(texto))
                return "";

            int separador = texto.IndexOf(' ');
            return separador > 0 ? texto.Substring(0, separador) : texto;
        }

        private void PreencherRequisitos(JsonElement matrix)
        {
            requisitosGrid.Rows.Clear();
            JsonElement rows;
            if (!matrix.TryGetProperty("Requirements", out rows) ||
                rows.ValueKind != JsonValueKind.Array)
                return;

            foreach (JsonElement row in rows.EnumerateArray())
            {
                if (row.ValueKind != JsonValueKind.Object)
                    continue;

                int rowIndex = requisitosGrid.Rows.Add(
                    LerPropriedade(row, "ID"),
                    LerPropriedade(row, "Requirement"));
                string requirementId = LerPropriedade(row, "ID");
                requisitosGrid.Rows[rowIndex].Tag = requirementId;
            }
        }

        private void PreencherConflitos(JsonElement matrix)
        {
            conflitosGrid.Rows.Clear();
            JsonElement rows;
            if (!matrix.TryGetProperty("Status by section", out rows) ||
                rows.ValueKind != JsonValueKind.Array)
                return;

            foreach (JsonElement row in rows.EnumerateArray())
            {
                if (row.ValueKind != JsonValueKind.Object)
                    continue;

                string estado = LerPropriedade(row, "Status");
                if (!estado.Contains("Conflict") &&
                    !estado.Contains("Partial") &&
                    !estado.Contains("No related"))
                    continue;

                conflitosGrid.Rows.Add(
                    LerPropriedade(row, "Section"),
                    LerPropriedade(row, "Page"),
                    LerPropriedade(row, "Requirements"),
                    LerPropriedade(row, "ITs assessed / suggested"),
                    estado,
                    LerPropriedade(row, "Changes vs previous version"));
            }

            if (conflitosGrid.Rows.Count == 0 &&
                matrix.TryGetProperty("Alerts", out JsonElement alerts) &&
                alerts.ValueKind == JsonValueKind.Array)
            {
                foreach (JsonElement alert in alerts.EnumerateArray())
                {
                    if (alert.ValueKind != JsonValueKind.Object)
                        continue;

                    conflitosGrid.Rows.Add(
                        LerPropriedade(alert, "Title"),
                        LerPropriedade(alert, "Date"),
                        LerPropriedade(alert, "Severity"),
                        LerPropriedade(alert, "IT"),
                        LerPropriedade(alert, "Type"),
                        LerPropriedade(alert, "Action"));
                }
            }
        }

        private void chatbotToolStripMenuItem_Click(object sender, EventArgs e)
        {
            Matriz.SelectedTab = CentralServidor;
            chatEntrada.Focus();
        }

        private void PreencherInstrucoes(JsonElement matrix)
        {
            instrucoesGrid.Rows.Clear();
            JsonElement rows;
            if (!matrix.TryGetProperty("Requirements", out rows) ||
                rows.ValueKind != JsonValueKind.Array)
                return;

            foreach (JsonElement row in rows.EnumerateArray())
            {
                if (row.ValueKind != JsonValueKind.Object)
                    continue;

                string descricao =
                    LerPropriedade(row, "Recommended action");
                if (string.IsNullOrWhiteSpace(descricao))
                    descricao = LerPropriedade(row, "Analysis");
                if (string.IsNullOrWhiteSpace(descricao))
                    descricao = LerPropriedade(row, "IT evidence");
                if (string.IsNullOrWhiteSpace(descricao))
                    descricao = LerPropriedade(row, "Requirement");

                if (string.IsNullOrWhiteSpace(descricao))
                    continue;

                int instructionRow = instrucoesGrid.Rows.Add(
                    LerPropriedade(row, "ID"),
                    descricao);
                instrucoesGrid.Rows[instructionRow].Tag =
                    LerPropriedade(row, "ID");
            }
        }

        private static string LerCelula(
            System.Collections.Generic.IList<JsonElement> cells,
            int index)
        {
            if (index >= cells.Count)
                return "";
            JsonElement value = cells[index];
            return value.ValueKind == JsonValueKind.String
                ? value.GetString() ?? ""
                : value.ToString();
        }

        private static string LerPropriedade(JsonElement row, string property)
        {
            JsonElement value;
            return row.TryGetProperty(property, out value)
                ? (value.ValueKind == JsonValueKind.String
                    ? value.GetString() ?? ""
                    : value.ToString())
                : "";
        }

        private void button1_Click(object sender, EventArgs e) { Close(); }
        private void button2_Click(object sender, EventArgs e) { WindowState = FormWindowState.Minimized; }
        private void button3_Click(object sender, EventArgs e)
        {
            WindowState = WindowState == FormWindowState.Maximized
                ? FormWindowState.Normal : FormWindowState.Maximized;
        }

        private void TitleBar_MouseDown(object sender, MouseEventArgs e)
        {
            if (e.Button != MouseButtons.Left) return;
            ReleaseCapture();
            SendMessage(Handle, WmNclButtonDown, HtCaption, 0);
        }

        private void menuStrip1_ItemClicked(object sender, ToolStripItemClickedEventArgs e) { }
        private void cooToolStripMenuItem_Click(object sender, EventArgs e)
        {
            Matriz.SelectedTab = CentralServidor;
        }
        private void dataGridView1_CellContentClick(object sender, DataGridViewCellEventArgs e) { }
        private void label1_Click(object sender, EventArgs e) { }
        private void sairToolStripMenuItem_Click(object sender, EventArgs e) { Close(); }
        private void abrirOutroProjetoToolStripMenuItem_Click(object sender, EventArgs e)
        {
            foreach (Form openForm in Application.OpenForms)
            {
                if (openForm is FormInicio)
                {
                    openForm.Show();
                    openForm.WindowState = FormWindowState.Normal;
                    Hide();
                    return;
                }
            }

            var formInicio = new FormInicio();
            formInicio.Show();
            Hide();
        }
        private void pedirCookiesToolStripMenuItem_Click(object sender, EventArgs e)
        {
            Matriz.SelectedTab = CentralServidor;
        }

        private void configuracoesCentralToolStripMenuItem_Click(object sender, EventArgs e)
        {

        }

        private void pedirCookiesToolStripMenuItem_Click_1(object sender, EventArgs e)
        {

        }



        private void TitleBar_Paint(object sender, PaintEventArgs e)
        {

        }

        private void chatEnviar_Click(object sender, EventArgs e)
        {
            _ = EnviarChatAsync();
        }

        private async Task EnviarChatAsync()
        {
            string message = chatEntrada.Text.Trim();
            if (string.IsNullOrWhiteSpace(message))
                return;

            AdicionarMensagem(true, message);
            chatHistory.Add(new Dictionary<string, string>
            {
                { "role", "user" },
                { "content", message }
            });
            chatEntrada.Clear();
            chatEnviar.Enabled = false;

            // A pergunta aparece logo (com um aviso enquanto o servidor responde): antes só se fazia scroll no fim,
            // por isso a pergunta ficava fora do ecrã até chegar a resposta
            // "A escrever." com as reticências a mudar (. .. ...) para se ver que está a funcionar
            AdicionarMensagem(false, AvisoFases[0]);
            int corpoAviso = chatHistorico.TextLength - AvisoFases[0].Length;
            chatHistorico.Refresh();
            var pararAviso = new System.Threading.CancellationTokenSource();
            Task animacao = AnimarAviso(corpoAviso, pararAviso.Token);

            try
            {
                var payload = JsonSerializer.Serialize(new
                {
                    message = message,
                    history = chatHistory
                });
                using (var content = new StringContent(
                    payload,
                    System.Text.Encoding.UTF8,
                    "application/json"))
                using (var response = await httpClient.PostAsync(
                    SERVER_URL + "/projects/" +
                    Uri.EscapeDataString(projetoNome) +
                    "/chat",
                    content))
                {
                    string json = await response.Content.ReadAsStringAsync();
                    if (!response.IsSuccessStatusCode)
                        throw new InvalidOperationException(json);

                    using (var result = JsonDocument.Parse(json))
                    {
                        string answer = result.RootElement.TryGetProperty("answer", out JsonElement answerElement)
                            ? answerElement.GetString() ?? ""
                            : "";
                        pararAviso.Cancel();
                        await animacao;
                        // A resposta é escrita no lugar do texto do aviso (o cabeçalho "ComplyAI • hora" fica). Não se
                        // apaga a mensagem do aviso: apagar a quebra de linha antes dela punha o último parágrafo da
                        // pergunta com o alinhamento do aviso (à esquerda).
                        // Sem lista de "Fontes": a resposta já cita requisitos, alertas, ITs e páginas
                        SubstituirFim(corpoAviso, "");
                        await EscreverResposta(answer);
                        chatHistory.Add(new Dictionary<string, string>
                        {
                            { "role", "assistant" },
                            { "content", answer }
                        });
                    }
                }
            }
            catch (Exception ex)
            {
                pararAviso.Cancel();
                await animacao;
                SubstituirFim(corpoAviso, "Não foi possível responder: " + ex.Message);
            }
            finally
            {
                chatEnviar.Enabled = true;
                chatHistorico.SelectionStart = chatHistorico.Text.Length;
                chatHistorico.ScrollToCaret();
            }
        }

        // Escreve uma mensagem no histórico do chat: cabeçalho a negrito (autor • hora), mensagens do utilizador à
        // direita e do ComplyAI à esquerda. Devolve onde a mensagem começa.
        // O histórico é só de leitura para o utilizador; o código tira essa proteção enquanto escreve (com ReadOnly
        // ligado o RichTextBox ignora alterações ao texto selecionado, por isso o aviso não saía).
        private int AdicionarMensagem(bool utilizador, string texto)
        {
            string cabecalho = (utilizador ? "Você" : "ComplyAI") + "  •  " + DateTime.Now.ToString("HH:mm");
            bool soLeitura = chatHistorico.ReadOnly;
            chatHistorico.ReadOnly = false;
            int inicio = chatHistorico.TextLength;
            string separador = inicio > 0 ? "\n\n" : "";
            chatHistorico.Select(inicio, 0);
            chatHistorico.SelectedText = separador + cabecalho + "\n" + (texto ?? "").Replace("\r\n", "\n");
            // alinhamento e letra só nos parágrafos da nova mensagem (depois do separador)
            int corpo = inicio + separador.Length;
            chatHistorico.Select(corpo, chatHistorico.TextLength - corpo);
            chatHistorico.SelectionAlignment = utilizador ? HorizontalAlignment.Right : HorizontalAlignment.Left;
            chatHistorico.SelectionFont = new Font(chatHistorico.Font, FontStyle.Regular);
            chatHistorico.Select(corpo, cabecalho.Length);
            chatHistorico.SelectionFont = new Font(chatHistorico.Font, FontStyle.Bold);
            chatHistorico.Select(chatHistorico.TextLength, 0);
            chatHistorico.ReadOnly = soLeitura;
            chatHistorico.ScrollToCaret();
            return inicio;
        }

        private static readonly string[] AvisoFases = { "A escrever.", "A escrever..", "A escrever..." };

        // Muda as reticências do aviso a cada 400 ms até a resposta chegar (o aviso é sempre o fim do texto)
        private async Task AnimarAviso(int corpo, System.Threading.CancellationToken parar)
        {
            int fase = 0;
            try
            {
                while (!parar.IsCancellationRequested)
                {
                    await Task.Delay(400, parar);
                    fase = (fase + 1) % AvisoFases.Length;
                    SubstituirFim(corpo, AvisoFases[fase]);
                }
            }
            catch (TaskCanceledException) { }
        }

        // Escreve a resposta no fim do histórico letra a letra, depressa: ~120 passos de 15 ms (cerca de 2 s), seja
        // qual for o tamanho
        private async Task EscreverResposta(string texto)
        {
            texto = (texto ?? "").Replace("\r\n", "\n");
            int passo = Math.Max(2, texto.Length / 120);
            for (int i = 0; i < texto.Length; i += passo)
            {
                SubstituirFim(chatHistorico.TextLength, texto.Substring(i, Math.Min(passo, texto.Length - i)));
                await Task.Delay(15);
            }
        }

        // Troca o texto desde `desde` até ao fim (desde = fim: acrescenta), com letra normal
        private void SubstituirFim(int desde, string texto)
        {
            if (desde < 0 || desde > chatHistorico.TextLength)
                return;
            bool soLeitura = chatHistorico.ReadOnly;
            chatHistorico.ReadOnly = false;
            chatHistorico.Select(desde, chatHistorico.TextLength - desde);
            chatHistorico.SelectionFont = new Font(chatHistorico.Font, FontStyle.Regular);
            chatHistorico.SelectedText = texto;
            chatHistorico.ReadOnly = soLeitura;
            chatHistorico.ScrollToCaret();
        }


        private async void descarregarMatrizToolStripMenuItem_Click(object sender, EventArgs e)
        {
            if (!activeDocumentId.HasValue)
            {
                MessageBox.Show(
                    "Não existe um documento ativo para exportar.",
                    "Matriz",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
                return;
            }

            using (var dialog = new SaveFileDialog())
            {
                dialog.Title = "Guardar matriz";
                dialog.Filter = "Excel (*.xlsx)|*.xlsx";
                dialog.FileName = "Matriz_" + projetoNome + "_" +
                                  activeDocumentId.Value + ".xlsx";
                if (dialog.ShowDialog(this) != DialogResult.OK)
                    return;

                try
                {
                    Cursor = Cursors.WaitCursor;
                    using (var response = await httpClient.GetAsync(
                        SERVER_URL + "/files/" +
                        Uri.EscapeDataString(projetoNome) + "/matrix/" +
                        activeDocumentId.Value))
                    {
                        response.EnsureSuccessStatusCode();
                        using (var stream = await response.Content.ReadAsStreamAsync())
                        using (var fileStream = File.Create(dialog.FileName))
                            await stream.CopyToAsync(fileStream);
                    }

                    MessageBox.Show(
                        "Matriz guardada com sucesso.",
                        "Exportação",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Information);
                }
                catch (Exception ex)
                {
                    MessageBox.Show(
                        "Não foi possível descarregar a matriz:\n\n" + ex.Message,
                        "Erro",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                }
                finally
                {
                    Cursor = Cursors.Default;
                }
            }
        }


        private async void dataGridView1_CellEndEdit(object sender, DataGridViewCellEventArgs e)
        {
            if (!activeDocumentId.HasValue ||
                e.RowIndex < 0 ||
                dataGridView1.Rows[e.RowIndex].Cells.Count < 5)
                return;

            DataGridViewRow row = dataGridView1.Rows[e.RowIndex];
            string section = row.Cells[0].Value as string;
            if (string.IsNullOrWhiteSpace(section))
                return;

            var payload = JsonSerializer.Serialize(new
            {
                section = section,
                process = row.Cells[2].Value as string,
                wsd = row.Cells[3].Value as string,
                wptgu = row.Cells[4].Value as string,
                updated_by = Environment.UserName
            });

            try
            {
                using (var content = new StringContent(
                    payload,
                    System.Text.Encoding.UTF8,
                    "application/json"))
                using (var request = new HttpRequestMessage(
                    new HttpMethod("PATCH"),
                    SERVER_URL + "/projects/" +
                    Uri.EscapeDataString(projetoNome) +
                    "/documents/" + activeDocumentId.Value + "/matrix")
                {
                    Content = content
                })
                using (var response = await httpClient.SendAsync(request))
                {
                    if (!response.IsSuccessStatusCode)
                        throw new InvalidOperationException(
                            await response.Content.ReadAsStringAsync());
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Não foi possível guardar a alteração:\n\n" + ex.Message,
                    "Erro",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }

        private async void requisitosGrid_CellDoubleClick(
            object sender,
            DataGridViewCellEventArgs e)
        {
            if (e.RowIndex < 0 ||
                requisitosGrid.Rows[e.RowIndex].Tag == null ||
                !activeDocumentId.HasValue)
                return;

            using (var dialog = new Form())
            {
                dialog.Text = "Confirmar requisito";
                dialog.FormBorderStyle = FormBorderStyle.FixedDialog;
                dialog.StartPosition = FormStartPosition.CenterParent;
                dialog.Width = 380;
                dialog.Height = 180;

                var approve = new Button
                {
                    Text = "Aprovar",
                    DialogResult = DialogResult.Yes,
                    Location = new Point(30, 70),
                    Size = new Size(90, 30)
                };
                var reject = new Button
                {
                    Text = "Rejeitar",
                    DialogResult = DialogResult.No,
                    Location = new Point(145, 70),
                    Size = new Size(90, 30)
                };
                var pending = new Button
                {
                    Text = "Pendente",
                    DialogResult = DialogResult.Retry,
                    Location = new Point(260, 70),
                    Size = new Size(90, 30)
                };

                dialog.Controls.Add(approve);
                dialog.Controls.Add(reject);
                dialog.Controls.Add(pending);

                DialogResult choice = dialog.ShowDialog(this);
                string status =
                    choice == DialogResult.Yes ? "approved" :
                    choice == DialogResult.No ? "rejected" :
                    choice == DialogResult.Retry ? "pending" : "";
                if (string.IsNullOrEmpty(status))
                    return;

                int requirementId;
                if (!int.TryParse(
                    requisitosGrid.Rows[e.RowIndex].Tag.ToString(),
                    out requirementId))
                    return;

                var payload = JsonSerializer.Serialize(new
                {
                    status = status,
                    reviewed_by = Environment.UserName
                });
                using (var content = new StringContent(
                    payload,
                    System.Text.Encoding.UTF8,
                    "application/json"))
                using (var request = new HttpRequestMessage(
                    new HttpMethod("PATCH"),
                    SERVER_URL + "/projects/" +
                    Uri.EscapeDataString(projetoNome) +
                    "/documents/" + activeDocumentId.Value +
                    "/requirements/" + requirementId)
                {
                    Content = content
                })
                using (var response = await httpClient.SendAsync(request))
                {
                    if (!response.IsSuccessStatusCode)
                        throw new InvalidOperationException(
                            await response.Content.ReadAsStringAsync());
                }

            }
        }

        private void chatEntrada_TextChanged(object sender, EventArgs e)
        {

        }

        private void chatEntrada_KeyDown(object sender, KeyEventArgs e)
        {
            if (e.KeyCode == Keys.Enter)
            {
                e.SuppressKeyPress = true;
                if (chatEnviar.Enabled)
                    chatEnviar.PerformClick();
            }
        }

        private async void enviarResolucaoConflitos_Click(
            object sender,
            EventArgs e)
        {
            if (!activeDocumentId.HasValue)
            {
                MessageBox.Show(
                    "Não existe um documento ativo.",
                    "Resolução de conflitos",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
                return;
            }

            var resolutions = new List<object>();
            foreach (DataGridViewRow row in conflitosGrid.Rows)
            {
                string resolution = row.Cells[5].Value as string ?? "";
                if (string.IsNullOrWhiteSpace(resolution))
                    continue;

                resolutions.Add(new
                {
                    section = row.Cells[0].Value as string,
                    page = row.Cells[1].Value as string,
                    requirements = row.Cells[2].Value as string,
                    it_assessed = row.Cells[3].Value as string,
                    status = row.Cells[4].Value as string,
                    resolution = resolution
                });
            }

            if (resolutions.Count == 0)
            {
                MessageBox.Show(
                    "Escreva pelo menos uma resolução na coluna Alterações.",
                    "Resolução de conflitos",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
                return;
            }

            var payload = JsonSerializer.Serialize(new
            {
                updated_by = Environment.UserName,
                resolutions = resolutions
            });

            try
            {
                enviarResolucaoConflitos.Enabled = false;
                using (var content = new StringContent(
                    payload,
                    System.Text.Encoding.UTF8,
                    "application/json"))
                using (var request = new HttpRequestMessage(
                    new HttpMethod("PATCH"),
                    SERVER_URL + "/projects/" +
                    Uri.EscapeDataString(projetoNome) +
                    "/documents/" + activeDocumentId.Value +
                    "/conflict-resolutions")
                {
                    Content = content
                })
                using (var response = await httpClient.SendAsync(request))
                {
                    if (!response.IsSuccessStatusCode)
                        throw new InvalidOperationException(
                            await response.Content.ReadAsStringAsync());

                    using (JsonDocument result = JsonDocument.Parse(
                        await response.Content.ReadAsStringAsync()))
                    {
                        int saved = result.RootElement.GetProperty("resolutions_saved").GetInt32();
                        MessageBox.Show(
                            saved + " resolução(ões) enviada(s) ao servidor.",
                            "Resolução de conflitos",
                            MessageBoxButtons.OK,
                            MessageBoxIcon.Information);
                    }
                }
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Não foi possível enviar as resoluções:\n\n" + ex.Message,
                    "Erro",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
            finally
            {
                enviarResolucaoConflitos.Enabled = true;
            }
        }

        private void requisitosGrid_CellEndEdit(
            object sender,
            DataGridViewCellEventArgs e)
        {
            if (e.RowIndex < 0 || e.ColumnIndex < 0)
                return;

            DataGridViewRow row = requisitosGrid.Rows[e.RowIndex];
            if (row.Tag == null)
                return;

            int requirementId;
            if (!int.TryParse(row.Tag.ToString(), out requirementId))
                return;

            string requirementDescription = row.Cells[1].Value as string ?? "";
            alteracoesRequisitos[requirementId] =
                JsonSerializer.Serialize(new
                {
                    requirement = requirementDescription,
                    status = "edited"
                });
        }

        private void instrucoesGrid_CellEndEdit(
            object sender,
            DataGridViewCellEventArgs e)
        {
            if (e.RowIndex < 0)
                return;

            DataGridViewRow row = instrucoesGrid.Rows[e.RowIndex];
            string instructionId = row.Tag == null
                ? "row-" + e.RowIndex
                : row.Tag.ToString();
            int key;
            if (!int.TryParse(instructionId, out key))
                key = e.RowIndex + 100000;

            string action = row.Cells[1].Value as string ?? "";
            alteracoesInstrucoes[key] =
                JsonSerializer.Serialize(new
                {
                    instruction = instructionId,
                    action = action
                });
        }

        private async void enviarAlteracoesToolStripMenuItem_Click(
            object sender,
            EventArgs e)
        {
            if (!activeDocumentId.HasValue)
            {
                MessageBox.Show(
                    "Não existe um documento ativo.",
                    "Alterações",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
                return;
            }

            if (alteracoesRequisitos.Count == 0 &&
                alteracoesInstrucoes.Count == 0)
            {
                MessageBox.Show(
                    "Não existem alterações pendentes.",
                    "Alterações",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
                return;
            }

            var payload = JsonSerializer.Serialize(new
            {
                updated_by = Environment.UserName,
                requirements = alteracoesRequisitos,
                instructions = alteracoesInstrucoes
            });

            try
            {
                using (var content = new StringContent(
                    payload,
                    System.Text.Encoding.UTF8,
                    "application/json"))
                using (var request = new HttpRequestMessage(
                    new HttpMethod("PATCH"),
                    SERVER_URL + "/projects/" +
                    Uri.EscapeDataString(projetoNome) +
                    "/documents/" + activeDocumentId.Value + "/changes")
                {
                    Content = content
                })
                using (var response = await httpClient.SendAsync(request))
                {
                    if (!response.IsSuccessStatusCode)
                        throw new InvalidOperationException(
                            await response.Content.ReadAsStringAsync());
                }

                alteracoesRequisitos.Clear();
                alteracoesInstrucoes.Clear();
                MessageBox.Show(
                    "Alterações enviadas ao servidor.",
                    "Alterações",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Information);
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Não foi possível enviar as alterações:\n\n" + ex.Message,
                    "Erro",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);
            }
        }
    }
}
