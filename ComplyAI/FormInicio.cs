
using System;
using System.IO;
using System.IO.Compression;
using System.Net.Http;
using System.Text.Json;
using System.Collections.Generic;
using System.Threading.Tasks;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace ComplyAI
{
    public partial class FormInicio : Form
    {
        private const string SERVER_URL = "http://localhost:9000";

        private static readonly HttpClient httpClient = new HttpClient()
        {
            Timeout = TimeSpan.FromMinutes(5)
        };

        private readonly string PROJECTS_DIR =
            Path.Combine(
                Environment.GetFolderPath(
                    Environment.SpecialFolder.LocalApplicationData), "ComplyAI", "Projects");

        [DllImport("user32.dll")]
        private static extern bool ReleaseCapture();

        [DllImport("user32.dll")]
        private static extern int SendMessage(
            IntPtr hWnd, int Msg, int wParam, int lParam);

        private const int WM_NCLBUTTONDOWN = 0xA1;
        private const int HTCAPTION = 0x2;

        private System.Windows.Forms.Timer timerLigacao;
        private bool verificacaoEmCurso = false;

        public FormInicio()
        {
            InitializeComponent();
        }

        private async void FormInicio_Load(object sender, EventArgs e)
        {
            await VerificarLigacaoServidor();

            timerLigacao = new System.Windows.Forms.Timer();
            timerLigacao.Interval = 5000;
            timerLigacao.Tick += TimerLigacao_Tick;
            timerLigacao.Start();
        }

        private async void TimerLigacao_Tick(object sender, EventArgs e)
        {
            if (verificacaoEmCurso)
                return;

            verificacaoEmCurso = true;

            try
            {
                using (var response = await httpClient.GetAsync(SERVER_URL + "/projects"))
                {
                    if (response.IsSuccessStatusCode)
                    {
                        lblEstadoLigacao.Text = "Servidor ligado";
                        lblEstadoLigacao.ForeColor = Color.Green;
                    }
                    else
                    {
                        lblEstadoLigacao.Text = "Servidor indisponível";
                        lblEstadoLigacao.ForeColor = Color.Red;
                    }
                }
            }
            catch
            {
                lblEstadoLigacao.Text = "Ligação ao servidor perdida!";
                lblEstadoLigacao.ForeColor = Color.Red;
            }
            finally
            {
                verificacaoEmCurso = false;
            }
        }

        private async Task VerificarLigacaoServidor()
        {
            try
            {
                lblEstadoLigacao.Text = "A verificar ligação ao servidor...";
                lblEstadoLigacao.ForeColor = Color.DarkOrange;

                btnVerProjetos.Enabled = false;

                using (var response = await httpClient.GetAsync(
                    SERVER_URL + "/projects"))
                {
                    if (response.IsSuccessStatusCode)
                    {
                        lblEstadoLigacao.Text = "Servidor ligado";
                        lblEstadoLigacao.ForeColor = Color.Green;

                        btnVerProjetos.Enabled = true;
                    }
                    else
                    {
                        lblEstadoLigacao.Text = "Servidor indisponível";
                        lblEstadoLigacao.ForeColor = Color.Red;
                    }
                }
            }
            catch
            {
                lblEstadoLigacao.Text = "Sem ligação ao servidor";
                lblEstadoLigacao.ForeColor = Color.Red;
            }
        }

        private void ArrastarFormulario(
            object sender, MouseEventArgs e)
        {
            if (e.Button == MouseButtons.Left)
            {
                ReleaseCapture();
                SendMessage(
                    Handle, WM_NCLBUTTONDOWN, HTCAPTION, 0);
            }
        }

        private void btnMinimizar_Click(object sender, EventArgs e)
        {
            WindowState = FormWindowState.Minimized;
        }

        private void btnMaximizar_Click(object sender, EventArgs e)
        {
            WindowState = WindowState == FormWindowState.Maximized
                ? FormWindowState.Normal : FormWindowState.Maximized;
        }

        private void btnFechar_Click(object sender, EventArgs e)
        {
            Close();
        }

        private void pbLogo_Click(object sender, EventArgs e)
        {
        }

        private void barraSuperior_Paint(object sender, PaintEventArgs e)
        {

        }

        private async void btnVerProjetos_Click(object sender, EventArgs e)
        {
            try
            {
                btnVerProjetos.Enabled = false;

                lblEstadoLigacao.Text = "A obter projetos...";
                lstProjetos.Items.Clear();

                var response = await httpClient.GetAsync(
                    SERVER_URL + "/projects");

                response.EnsureSuccessStatusCode();

                string json = await response.Content.ReadAsStringAsync();

                var resultado = JsonSerializer.Deserialize<ProjectsResponse>(
                    json,
                    new JsonSerializerOptions
                    {
                        PropertyNameCaseInsensitive = true
                    });

                if (resultado == null ||
                    resultado.projects == null ||
                    resultado.projects.Count == 0)
                {
                    lblEstadoLigacao.Text = "Não existem projetos disponíveis.";
                    return;
                }

                foreach (string projeto in resultado.projects)
                {
                    lstProjetos.Items.Add(projeto);
                }

                lblEstadoLigacao.Text =
                    resultado.projects.Count + " projeto(s) encontrado(s).";
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Erro ao obter projetos:\n\n" + ex.Message,
                    "Erro de comunicação",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);

                lblEstadoLigacao.Text = "Erro de ligação ao servidor.";
            }
            finally
            {
                btnVerProjetos.Enabled = true;
            }
        }

        private async void lstProjetos_SelectedIndexChanged(object sender, EventArgs e)
        {
            if (lstProjetos.SelectedItem == null)
                return;

            string projeto = lstProjetos.SelectedItem.ToString();

            await CarregarProjeto(projeto);
        }

        private async Task CarregarProjeto(string projeto)
        {
            try
            {
                lstProjetos.Enabled = false;
                btnVerProjetos.Enabled = false;

                lblEstadoLigacao.Text = "A descarregar projeto...";

                Directory.CreateDirectory(PROJECTS_DIR);

                string projetoPath = Path.Combine(PROJECTS_DIR, projeto);
                string zipPath = Path.Combine(PROJECTS_DIR, projeto + ".zip");

                string url = SERVER_URL + "/projects/" +
                             Uri.EscapeDataString(projeto) + "/download";

                // Download Zip
                using (var response = await httpClient.GetAsync(url))
                {
                    response.EnsureSuccessStatusCode();

                    using (var stream = await response.Content.ReadAsStreamAsync())
                    using (var fileStream = File.Create(zipPath))
                    {
                        await stream.CopyToAsync(fileStream);
                    }
                }

                lblEstadoLigacao.Text = "A extrair documentos...";

                // Eliminar cópia anterior
                if (Directory.Exists(projetoPath))
                {
                    Directory.Delete(projetoPath, true);
                }

                // Extrair ficheiros
                ZipFile.ExtractToDirectory(zipPath, projetoPath);

                File.Delete(zipPath);

                lblEstadoLigacao.Text = "A comunicar com o servidor...";

                // Informar o servidor
                string loadedUrl = SERVER_URL + "/projects/" +
                                   Uri.EscapeDataString(projeto) + "/loaded";

                using (var response = await httpClient.PostAsync(
                    loadedUrl, null))
                {
                    response.EnsureSuccessStatusCode();
                }

                // Abrir Form1
                Form1 form = new Form1(projetoPath);

                form.Show();

                this.Hide();
            }
            catch (Exception ex)
            {
                MessageBox.Show(
                    "Não foi possível carregar o projeto:\n\n" + ex.Message,
                    "Erro",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Error);

                lblEstadoLigacao.Text = "Erro ao carregar projeto.";
            }
            finally
            {
                lstProjetos.Enabled = true;
                btnVerProjetos.Enabled = true;
            }
        }

        public class ProjectsResponse
        {
            public List<string> projects { get; set; }
        }
    }
}
