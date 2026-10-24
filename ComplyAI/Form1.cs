using System;
using System.Drawing;
using System.Runtime.InteropServices;
using System.Windows.Forms;

namespace ComplyAI
{
    public partial class Form1 : Form
    {
        private const int WmNclButtonDown = 0x00A1;
        private const int HtCaption = 0x2;

        [DllImport("user32.dll")]
        private static extern bool ReleaseCapture();

        [DllImport("user32.dll")]
        private static extern IntPtr SendMessage(IntPtr hWnd, int msg, int wParam, int lParam);

        public Form1()
        {
            InitializeComponent();
            AddExampleTables();

            Text = "ComplyAI";
            TitleBar.MouseDown += TitleBar_MouseDown;
            menuStrip1.MouseDown += TitleBar_MouseDown;
            button1.BringToFront();
            button2.BringToFront();
            button3.BringToFront();
            sairToolStripMenuItem.Click += sairToolStripMenuItem_Click;
            abrirOutroProjetoToolStripMenuItem.Click += abrirOutroProjetoToolStripMenuItem_Click;
            pedirCookiesToolStripMenuItem.Click += pedirCookiesToolStripMenuItem_Click;
        }

        private void AddExampleTables()
        {
            AddExampleTable(
                Instrucoes,
                "Nº da instrução",
                new[]
                {
                    new[] { "INST-001", "Verificar a documentação antes de iniciar o processo." },
                    new[] { "INST-002", "Registar todas as alterações realizadas no projeto." }
                });

            AddExampleTable(
                Normas,
                "Nº da norma",
                new[]
                {
                    new[] { "ISO-9001", "Garantir a qualidade e a melhoria contínua dos processos." },
                    new[] { "ISO-14001", "Controlar os impactos ambientais das atividades." }
                });

            AddExampleTable(
                Requisitos,
                "Nº do requisito",
                new[]
                {
                    new[] { "REQ-001", "O sistema deve permitir consultar os documentos aprovados." },
                    new[] { "REQ-002", "O utilizador deve conseguir acompanhar o estado do processo." }
                });
        }

        private static void AddExampleTable(TabPage tabPage, string numberHeader, string[][] rows)
        {
            var table = new DataGridView
            {
                Name = "TabelaExemplo",
                Dock = DockStyle.Fill,
                BackgroundColor = Color.White,
                BorderStyle = BorderStyle.None,
                AllowUserToAddRows = false,
                AllowUserToDeleteRows = false,
                ReadOnly = true,
                RowHeadersVisible = false,
                SelectionMode = DataGridViewSelectionMode.FullRowSelect,
                AutoSizeRowsMode = DataGridViewAutoSizeRowsMode.AllCells,
                EnableHeadersVisualStyles = false
            };

            table.ColumnHeadersDefaultCellStyle = new DataGridViewCellStyle
            {
                BackColor = Color.FromArgb(0, 61, 136),
                ForeColor = Color.White,
                Font = new Font("Segoe UI", 9F, FontStyle.Bold),
                SelectionBackColor = Color.FromArgb(0, 61, 136)
            };
            table.DefaultCellStyle = new DataGridViewCellStyle
            {
                Font = new Font("Segoe UI", 9F),
                SelectionBackColor = Color.FromArgb(219, 234, 254),
                SelectionForeColor = Color.FromArgb(15, 23, 42),
                WrapMode = DataGridViewTriState.True
            };
            table.AlternatingRowsDefaultCellStyle.BackColor = Color.FromArgb(248, 250, 252);
            table.Columns.Add("Numero", numberHeader);
            table.Columns.Add("Texto", "Texto");
            table.Columns["Numero"].Width = 150;
            table.Columns["Texto"].AutoSizeMode = DataGridViewAutoSizeColumnMode.Fill;
            foreach (var row in rows)
            {
                table.Rows.Add(row[0], row[1]);
            }

            tabPage.Controls.Add(table);
            table.BringToFront();
            table.Visible = true;
            tabPage.PerformLayout();
        }

        private void button1_Click(object sender, EventArgs e)
        {
            Close();
        }

        private void button2_Click(object sender, EventArgs e)
        {
            WindowState = FormWindowState.Minimized;
        }

        private void button3_Click(object sender, EventArgs e)
        {
            WindowState = WindowState == FormWindowState.Maximized
                ? FormWindowState.Normal
                : FormWindowState.Maximized;
        }

        private void TitleBar_MouseDown(object sender, MouseEventArgs e)
        {
            if (e.Button != MouseButtons.Left)
            {
                return;
            }

            ReleaseCapture();
            SendMessage(Handle, WmNclButtonDown, HtCaption, 0);
        }

        private void menuStrip1_ItemClicked(object sender, ToolStripItemClickedEventArgs e)
        {
        }

        private void cooToolStripMenuItem_Click(object sender, EventArgs e)
        {
        }

        private void dataGridView1_CellContentClick(object sender, DataGridViewCellEventArgs e)
        {
        }

        private void label1_Click(object sender, EventArgs e)
        {
        }

        private void sairToolStripMenuItem_Click(object sender, EventArgs e)
        {
            Close();
        }

        private void abrirOutroProjetoToolStripMenuItem_Click(object sender, EventArgs e)
        {
            MessageBox.Show("A abertura de outro projeto será disponibilizada em breve.",
                "Projetos", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }

        private void pedirCookiesToolStripMenuItem_Click(object sender, EventArgs e)
        {
            MessageBox.Show("A solicitação de cookies será disponibilizada em breve.",
                "Cookies", MessageBoxButtons.OK, MessageBoxIcon.Information);
        }
    }
}
