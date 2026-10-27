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
            MessageBox.Show("A abertura de outro projeto será disponibilizada em breve.",
                "Projetos", MessageBoxButtons.OK, MessageBoxIcon.Information);
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

        private void perguntasServidorToolStripMenuItem_Click(object sender, EventArgs e)
        {

        }

        private void atualizacoesCard_Paint(object sender, PaintEventArgs e)
        {

        }

        private void perguntasBotao_Click(object sender, EventArgs e)
        {

        }
    }
}
