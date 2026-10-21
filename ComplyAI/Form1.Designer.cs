namespace ComplyAI
{
    partial class Form1
    {
        /// <summary>
        /// Required designer variable.
        /// </summary>
        private System.ComponentModel.IContainer components = null;

        /// <summary>
        /// Clean up any resources being used.
        /// </summary>
        /// <param name="disposing">true if managed resources should be disposed; otherwise, false.</param>
        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }
            base.Dispose(disposing);
        }

        #region Windows Form Designer generated code

        /// <summary>
        /// Required method for Designer support - do not modify
        /// the contents of this method with the code editor.
        /// </summary>
        private void InitializeComponent()
        {
            this.TitleBar = new System.Windows.Forms.Panel();
            this.button3 = new System.Windows.Forms.Button();
            this.button2 = new System.Windows.Forms.Button();
            this.button1 = new System.Windows.Forms.Button();
            this.menuStrip1 = new System.Windows.Forms.MenuStrip();
            this.projectsToolStripMenuItem = new System.Windows.Forms.ToolStripMenuItem();
            this.abrirOutroProjetoToolStripMenuItem = new System.Windows.Forms.ToolStripMenuItem();
            this.sairToolStripMenuItem = new System.Windows.Forms.ToolStripMenuItem();
            this.cooToolStripMenuItem = new System.Windows.Forms.ToolStripMenuItem();
            this.pedirCookiesToolStripMenuItem = new System.Windows.Forms.ToolStripMenuItem();
            this.Matriz = new System.Windows.Forms.TabControl();
            this.tabPage1 = new System.Windows.Forms.TabPage();
            this.dataGridView1 = new System.Windows.Forms.DataGridView();
            this.Conteudo = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Página = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Processo_LEONI = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.PROC_WSD = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.PROC_WPTGU = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Normas = new System.Windows.Forms.TabPage();
            this.Requisitos = new System.Windows.Forms.TabPage();
            this.Instrucoes = new System.Windows.Forms.TabPage();
            this.label1 = new System.Windows.Forms.Label();
            this.label2 = new System.Windows.Forms.Label();
            this.TitleBar.SuspendLayout();
            this.menuStrip1.SuspendLayout();
            this.Matriz.SuspendLayout();
            this.tabPage1.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)(this.dataGridView1)).BeginInit();
            this.SuspendLayout();
            // 
            // TitleBar
            // 
            this.TitleBar.Controls.Add(this.button3);
            this.TitleBar.Controls.Add(this.button2);
            this.TitleBar.Controls.Add(this.button1);
            this.TitleBar.Controls.Add(this.menuStrip1);
            this.TitleBar.Dock = System.Windows.Forms.DockStyle.Top;
            this.TitleBar.Location = new System.Drawing.Point(0, 0);
            this.TitleBar.Name = "TitleBar";
            this.TitleBar.Size = new System.Drawing.Size(1503, 23);
            this.TitleBar.TabIndex = 0;
            // 
            // button3
            // 
            this.button3.Location = new System.Drawing.Point(1454, 3);
            this.button3.Name = "button3";
            this.button3.Size = new System.Drawing.Size(20, 20);
            this.button3.TabIndex = 3;
            this.button3.Text = "_";
            this.button3.UseVisualStyleBackColor = true;
            this.button3.Click += new System.EventHandler(this.button3_Click_1);
            // 
            // button2
            // 
            this.button2.Location = new System.Drawing.Point(1428, 3);
            this.button2.Name = "button2";
            this.button2.Size = new System.Drawing.Size(20, 20);
            this.button2.TabIndex = 2;
            this.button2.Text = "_";
            this.button2.UseVisualStyleBackColor = true;
            this.button2.Click += new System.EventHandler(this.button2_Click_1);
            // 
            // button1
            // 
            this.button1.Location = new System.Drawing.Point(1480, 3);
            this.button1.Name = "button1";
            this.button1.Size = new System.Drawing.Size(20, 20);
            this.button1.TabIndex = 1;
            this.button1.Text = "X";
            this.button1.UseVisualStyleBackColor = true;
            this.button1.Click += new System.EventHandler(this.button1_Click);
            // 
            // menuStrip1
            // 
            this.menuStrip1.Items.AddRange(new System.Windows.Forms.ToolStripItem[] {
            this.projectsToolStripMenuItem,
            this.cooToolStripMenuItem});
            this.menuStrip1.Location = new System.Drawing.Point(0, 0);
            this.menuStrip1.Name = "menuStrip1";
            this.menuStrip1.Size = new System.Drawing.Size(1503, 24);
            this.menuStrip1.TabIndex = 0;
            this.menuStrip1.Text = "menuStrip1";
            this.menuStrip1.ItemClicked += new System.Windows.Forms.ToolStripItemClickedEventHandler(this.menuStrip1_ItemClicked);
            // 
            // projectsToolStripMenuItem
            // 
            this.projectsToolStripMenuItem.DropDownItems.AddRange(new System.Windows.Forms.ToolStripItem[] {
            this.abrirOutroProjetoToolStripMenuItem,
            this.sairToolStripMenuItem});
            this.projectsToolStripMenuItem.Name = "projectsToolStripMenuItem";
            this.projectsToolStripMenuItem.Size = new System.Drawing.Size(61, 20);
            this.projectsToolStripMenuItem.Text = "Projects";
            this.projectsToolStripMenuItem.Click += new System.EventHandler(this.projectsToolStripMenuItem_Click);
            // 
            // abrirOutroProjetoToolStripMenuItem
            // 
            this.abrirOutroProjetoToolStripMenuItem.Name = "abrirOutroProjetoToolStripMenuItem";
            this.abrirOutroProjetoToolStripMenuItem.Size = new System.Drawing.Size(180, 22);
            this.abrirOutroProjetoToolStripMenuItem.Text = "Abrir Outro Projeto";
            // 
            // sairToolStripMenuItem
            // 
            this.sairToolStripMenuItem.Name = "sairToolStripMenuItem";
            this.sairToolStripMenuItem.Size = new System.Drawing.Size(180, 22);
            this.sairToolStripMenuItem.Text = "Sair";
            // 
            // cooToolStripMenuItem
            // 
            this.cooToolStripMenuItem.DropDownItems.AddRange(new System.Windows.Forms.ToolStripItem[] {
            this.pedirCookiesToolStripMenuItem});
            this.cooToolStripMenuItem.Name = "cooToolStripMenuItem";
            this.cooToolStripMenuItem.Size = new System.Drawing.Size(61, 20);
            this.cooToolStripMenuItem.Text = "Cookies";
            this.cooToolStripMenuItem.Click += new System.EventHandler(this.cooToolStripMenuItem_Click);
            // 
            // pedirCookiesToolStripMenuItem
            // 
            this.pedirCookiesToolStripMenuItem.Name = "pedirCookiesToolStripMenuItem";
            this.pedirCookiesToolStripMenuItem.Size = new System.Drawing.Size(180, 22);
            this.pedirCookiesToolStripMenuItem.Text = "Pedir Cookies";
            // 
            // Matriz
            // 
            this.Matriz.Controls.Add(this.tabPage1);
            this.Matriz.Controls.Add(this.Normas);
            this.Matriz.Controls.Add(this.Requisitos);
            this.Matriz.Controls.Add(this.Instrucoes);
            this.Matriz.Cursor = System.Windows.Forms.Cursors.Default;
            this.Matriz.Location = new System.Drawing.Point(0, 56);
            this.Matriz.Name = "Matriz";
            this.Matriz.SelectedIndex = 0;
            this.Matriz.Size = new System.Drawing.Size(1503, 522);
            this.Matriz.TabIndex = 1;
            // 
            // tabPage1
            // 
            this.tabPage1.Controls.Add(this.dataGridView1);
            this.tabPage1.Location = new System.Drawing.Point(4, 22);
            this.tabPage1.Name = "tabPage1";
            this.tabPage1.Padding = new System.Windows.Forms.Padding(3);
            this.tabPage1.Size = new System.Drawing.Size(1495, 496);
            this.tabPage1.TabIndex = 0;
            this.tabPage1.Text = "Matrix";
            this.tabPage1.UseVisualStyleBackColor = true;
            // 
            // dataGridView1
            // 
            this.dataGridView1.AllowUserToAddRows = false;
            this.dataGridView1.AllowUserToDeleteRows = false;
            this.dataGridView1.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dataGridView1.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.Conteudo,
            this.Página,
            this.Processo_LEONI,
            this.PROC_WSD,
            this.PROC_WPTGU});
            this.dataGridView1.Location = new System.Drawing.Point(8, 6);
            this.dataGridView1.Name = "dataGridView1";
            this.dataGridView1.ReadOnly = true;
            this.dataGridView1.Size = new System.Drawing.Size(1479, 484);
            this.dataGridView1.TabIndex = 0;
            this.dataGridView1.CellContentClick += new System.Windows.Forms.DataGridViewCellEventHandler(this.dataGridView1_CellContentClick);
            // 
            // Conteudo
            // 
            this.Conteudo.FillWeight = 450F;
            this.Conteudo.HeaderText = "Conteudo";
            this.Conteudo.Name = "Conteudo";
            this.Conteudo.ReadOnly = true;
            this.Conteudo.Width = 450;
            // 
            // Página
            // 
            this.Página.HeaderText = "Pagina";
            this.Página.Name = "Página";
            this.Página.ReadOnly = true;
            // 
            // Processo_LEONI
            // 
            this.Processo_LEONI.FillWeight = 200F;
            this.Processo_LEONI.HeaderText = "Processo LEONI";
            this.Processo_LEONI.Name = "Processo_LEONI";
            this.Processo_LEONI.ReadOnly = true;
            this.Processo_LEONI.Width = 200;
            // 
            // PROC_WSD
            // 
            this.PROC_WSD.FillWeight = 300F;
            this.PROC_WSD.HeaderText = "PROC. WSD";
            this.PROC_WSD.Name = "PROC_WSD";
            this.PROC_WSD.ReadOnly = true;
            this.PROC_WSD.Width = 300;
            // 
            // PROC_WPTGU
            // 
            this.PROC_WPTGU.FillWeight = 300F;
            this.PROC_WPTGU.HeaderText = "PROC. WPTGU";
            this.PROC_WPTGU.Name = "PROC_WPTGU";
            this.PROC_WPTGU.ReadOnly = true;
            this.PROC_WPTGU.Width = 300;
            // 
            // Normas
            // 
            this.Normas.Location = new System.Drawing.Point(4, 22);
            this.Normas.Name = "Normas";
            this.Normas.Padding = new System.Windows.Forms.Padding(3);
            this.Normas.Size = new System.Drawing.Size(1495, 496);
            this.Normas.TabIndex = 1;
            this.Normas.Text = "Normas";
            this.Normas.UseVisualStyleBackColor = true;
            // 
            // Requisitos
            // 
            this.Requisitos.Location = new System.Drawing.Point(4, 22);
            this.Requisitos.Name = "Requisitos";
            this.Requisitos.Padding = new System.Windows.Forms.Padding(3);
            this.Requisitos.Size = new System.Drawing.Size(1495, 496);
            this.Requisitos.TabIndex = 2;
            this.Requisitos.Text = "Requisitos";
            this.Requisitos.UseVisualStyleBackColor = true;
            // 
            // Instrucoes
            // 
            this.Instrucoes.Location = new System.Drawing.Point(4, 22);
            this.Instrucoes.Name = "Instrucoes";
            this.Instrucoes.Padding = new System.Windows.Forms.Padding(3);
            this.Instrucoes.Size = new System.Drawing.Size(1495, 496);
            this.Instrucoes.TabIndex = 3;
            this.Instrucoes.Text = "Instruções";
            this.Instrucoes.UseVisualStyleBackColor = true;
            // 
            // label1
            // 
            this.label1.AutoSize = true;
            this.label1.Font = new System.Drawing.Font("Microsoft Sans Serif", 15F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(0)));
            this.label1.Location = new System.Drawing.Point(12, 26);
            this.label1.Name = "label1";
            this.label1.Size = new System.Drawing.Size(79, 25);
            this.label1.TabIndex = 2;
            this.label1.Text = "Cliente:";
            this.label1.Click += new System.EventHandler(this.label1_Click);
            // 
            // label2
            // 
            this.label2.AutoSize = true;
            this.label2.Font = new System.Drawing.Font("Microsoft Sans Serif", 15F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(0)));
            this.label2.Location = new System.Drawing.Point(312, 26);
            this.label2.Name = "label2";
            this.label2.Size = new System.Drawing.Size(66, 25);
            this.label2.TabIndex = 3;
            this.label2.Text = "Titulo:";
            // 
            // Form1
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(6F, 13F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(1503, 585);
            this.Controls.Add(this.label2);
            this.Controls.Add(this.label1);
            this.Controls.Add(this.Matriz);
            this.Controls.Add(this.TitleBar);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.None;
            this.MainMenuStrip = this.menuStrip1;
            this.Name = "Form1";
            this.Text = "Form1";
            this.TitleBar.ResumeLayout(false);
            this.TitleBar.PerformLayout();
            this.menuStrip1.ResumeLayout(false);
            this.menuStrip1.PerformLayout();
            this.Matriz.ResumeLayout(false);
            this.tabPage1.ResumeLayout(false);
            ((System.ComponentModel.ISupportInitialize)(this.dataGridView1)).EndInit();
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion

        private System.Windows.Forms.Panel TitleBar;
        private System.Windows.Forms.Button button1;
        private System.Windows.Forms.MenuStrip menuStrip1;
        private System.Windows.Forms.ToolStripMenuItem projectsToolStripMenuItem;
        private System.Windows.Forms.Button button2;
        private System.Windows.Forms.Button button3;
        private System.Windows.Forms.ToolStripMenuItem cooToolStripMenuItem;
        private System.Windows.Forms.ToolStripMenuItem abrirOutroProjetoToolStripMenuItem;
        private System.Windows.Forms.ToolStripMenuItem sairToolStripMenuItem;
        private System.Windows.Forms.ToolStripMenuItem pedirCookiesToolStripMenuItem;
        private System.Windows.Forms.TabControl Matriz;
        private System.Windows.Forms.TabPage tabPage1;
        private System.Windows.Forms.TabPage Normas;
        private System.Windows.Forms.DataGridView dataGridView1;
        private System.Windows.Forms.DataGridViewTextBoxColumn Conteudo;
        private System.Windows.Forms.DataGridViewTextBoxColumn Página;
        private System.Windows.Forms.DataGridViewTextBoxColumn Processo_LEONI;
        private System.Windows.Forms.DataGridViewTextBoxColumn PROC_WSD;
        private System.Windows.Forms.DataGridViewTextBoxColumn PROC_WPTGU;
        private System.Windows.Forms.TabPage Requisitos;
        private System.Windows.Forms.TabPage Instrucoes;
        private System.Windows.Forms.Label label1;
        private System.Windows.Forms.Label label2;
    }
}

