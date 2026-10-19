using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Drawing;
using System.Linq;
using System.Text;
using System.Threading.Tasks;
using System.Windows.Forms;

namespace ComplyAI
{
    public partial class Form1 : Form
    {
        public Form1()
        {
            InitializeComponent();
        }

        private void button1_Click(object sender, EventArgs e)
        {

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

        private void listBoxNav_SelectedIndexChanged(object sender, EventArgs e)
        {
            var lb = sender as ListBox;
            if (lb == null) return;
            var idx = lb.SelectedIndex;
            this.panelMatrix.Visible = (idx == 0);
            this.panelNormas.Visible = (idx == 1);
            this.panelRequisitos.Visible = (idx == 2);
            this.panelInstrucoes.Visible = (idx == 3);
        }

        private void button2_Click(object sender, EventArgs e)
        {

        }
    }
}
