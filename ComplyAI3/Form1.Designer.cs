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
            this.toolStrip1 = new System.Windows.Forms.ToolStrip();
            this.toolStripComboBoxProject = new System.Windows.Forms.ToolStripComboBox();
            this.toolStripTextBoxSearch = new System.Windows.Forms.ToolStripTextBox();
            this.toolStripButtonRefresh = new System.Windows.Forms.ToolStripButton();
            this.splitContainerMain = new System.Windows.Forms.SplitContainer();
            this.listBoxNav = new System.Windows.Forms.ListBox();
            this.panelMatrix = new System.Windows.Forms.Panel();
            this.panelNormas = new System.Windows.Forms.Panel();
            this.panelRequisitos = new System.Windows.Forms.Panel();
            this.panelInstrucoes = new System.Windows.Forms.Panel();
            this.dataGridView1 = new System.Windows.Forms.DataGridView();
            this.dataGridViewNormas = new System.Windows.Forms.DataGridView();
            this.dataGridViewRequisitos = new System.Windows.Forms.DataGridView();
            this.dataGridViewInstrucoes = new System.Windows.Forms.DataGridView();
            this.Conteudo = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Página = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Processo_LEONI = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.PROC_WSD = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.PROC_WPTGU = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Conteudo_N = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Pagina_N = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Processo_LEONI_N = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.PROC_WSD_N = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.PROC_WPTGU_N = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Conteudo_R = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Pagina_R = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Processo_LEONI_R = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.PROC_WSD_R = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.PROC_WPTGU_R = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Conteudo_I = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Pagina_I = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.Processo_LEONI_I = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.PROC_WSD_I = new System.Windows.Forms.DataGridViewTextBoxColumn();
            this.PROC_WPTGU_I = new System.Windows.Forms.DataGridViewTextBoxColumn();
            // removed TabPage initializers (using Panels instead)
            this.statusStrip1 = new System.Windows.Forms.StatusStrip();
            this.toolStripStatusLabel1 = new System.Windows.Forms.ToolStripStatusLabel();
            this.label1 = new System.Windows.Forms.Label();
            this.label2 = new System.Windows.Forms.Label();
            this.button1 = new System.Windows.Forms.Button();
            this.button2 = new System.Windows.Forms.Button();
            this.toolStrip1.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)(this.splitContainerMain)).BeginInit();
            this.splitContainerMain.Panel1.SuspendLayout();
            this.splitContainerMain.Panel2.SuspendLayout();
            this.splitContainerMain.SuspendLayout();
            this.panelMatrix.SuspendLayout();
            this.panelNormas.SuspendLayout();
            this.panelRequisitos.SuspendLayout();
            this.panelInstrucoes.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)(this.dataGridView1)).BeginInit();
            this.statusStrip1.SuspendLayout();
            this.SuspendLayout();
            // 
            // toolStrip1
            // 
            this.toolStrip1.GripStyle = System.Windows.Forms.ToolStripGripStyle.Hidden;
            this.toolStrip1.Items.AddRange(new System.Windows.Forms.ToolStripItem[] {
            this.toolStripComboBoxProject,
            this.toolStripTextBoxSearch,
            this.toolStripButtonRefresh});
            this.toolStrip1.Location = new System.Drawing.Point(0, 0);
            this.toolStrip1.Name = "toolStrip1";
            this.toolStrip1.Size = new System.Drawing.Size(1503, 25);
            this.toolStrip1.TabIndex = 0;
            // 
            // toolStripComboBoxProject
            // 
            this.toolStripComboBoxProject.AutoSize = false;
            this.toolStripComboBoxProject.Items.AddRange(new object[] {
            "Projeto A",
            "Projeto B"});
            this.toolStripComboBoxProject.Name = "toolStripComboBoxProject";
            this.toolStripComboBoxProject.Size = new System.Drawing.Size(200, 21);
            // 
            // toolStripTextBoxSearch
            // 
            this.toolStripTextBoxSearch.AutoSize = false;
            this.toolStripTextBoxSearch.Font = new System.Drawing.Font("Segoe UI", 9F);
            this.toolStripTextBoxSearch.Name = "toolStripTextBoxSearch";
            this.toolStripTextBoxSearch.Size = new System.Drawing.Size(250, 23);
            // 
            // toolStripButtonRefresh
            // 
            this.toolStripButtonRefresh.DisplayStyle = System.Windows.Forms.ToolStripItemDisplayStyle.Text;
            this.toolStripButtonRefresh.Name = "toolStripButtonRefresh";
            this.toolStripButtonRefresh.Size = new System.Drawing.Size(57, 22);
            this.toolStripButtonRefresh.Text = "Atualizar";
            this.toolStripButtonRefresh.Click += new System.EventHandler(this.button2_Click);
            // 
            // splitContainerMain
            // 
            this.splitContainerMain.Dock = System.Windows.Forms.DockStyle.Fill;
            this.splitContainerMain.Location = new System.Drawing.Point(0, 25);
            this.splitContainerMain.Name = "splitContainerMain";
            // 
            // splitContainerMain.Panel1
            // 
            this.splitContainerMain.Panel1.Controls.Add(this.listBoxNav);
            // 
            // splitContainerMain.Panel2
            // 
            // add panels to right side
            this.splitContainerMain.Panel2.Controls.Add(this.panelInstrucoes);
            this.splitContainerMain.Panel2.Controls.Add(this.panelRequisitos);
            this.splitContainerMain.Panel2.Controls.Add(this.panelNormas);
            this.splitContainerMain.Panel2.Controls.Add(this.panelMatrix);
            this.splitContainerMain.Size = new System.Drawing.Size(1503, 689);
            this.splitContainerMain.SplitterDistance = 220;
            this.splitContainerMain.TabIndex = 1;
            // 
            // listBoxNav
            // 
            this.listBoxNav.BorderStyle = System.Windows.Forms.BorderStyle.None;
            this.listBoxNav.Dock = System.Windows.Forms.DockStyle.Fill;
            this.listBoxNav.Font = new System.Drawing.Font("Segoe UI", 10F);
            this.listBoxNav.ItemHeight = 17;
            this.listBoxNav.Items.AddRange(new object[] {
            "Matrix",
            "Normas",
            "Requisitos",
            "Instruções"});
            this.listBoxNav.Location = new System.Drawing.Point(0, 0);
            this.listBoxNav.Name = "listBoxNav";
            this.listBoxNav.Size = new System.Drawing.Size(220, 689);
            this.listBoxNav.TabIndex = 0;
            this.listBoxNav.SelectedIndexChanged += new System.EventHandler(this.listBoxNav_SelectedIndexChanged);
            // 
            // panelMatrix (replaces former TabControl pages)
            // 
            // panelMatrix
            // 
            this.panelMatrix.Controls.Add(this.dataGridView1);
            this.panelMatrix.Dock = System.Windows.Forms.DockStyle.Fill;
            this.panelMatrix.Location = new System.Drawing.Point(0, 0);
            this.panelMatrix.Name = "panelMatrix";
            this.panelMatrix.Size = new System.Drawing.Size(1271, 661);
            this.panelMatrix.TabIndex = 0;
            this.panelMatrix.Visible = true;
            // 
            // dataGridView1
            // 
            this.dataGridView1.AllowUserToAddRows = false;
            this.dataGridView1.AllowUserToDeleteRows = false;
            this.dataGridView1.AllowUserToResizeRows = false;
            this.dataGridView1.AutoSizeColumnsMode = System.Windows.Forms.DataGridViewAutoSizeColumnsMode.Fill;
            this.dataGridView1.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dataGridView1.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.Conteudo,
            this.Página,
            this.Processo_LEONI,
            this.PROC_WSD,
            this.PROC_WPTGU});
            this.dataGridView1.Dock = System.Windows.Forms.DockStyle.Fill;
            this.dataGridView1.Location = new System.Drawing.Point(3, 3);
            this.dataGridView1.Name = "dataGridView1";
            this.dataGridView1.ReadOnly = true;
            this.dataGridView1.RowHeadersVisible = false;
            this.dataGridView1.SelectionMode = System.Windows.Forms.DataGridViewSelectionMode.FullRowSelect;
            this.dataGridView1.Size = new System.Drawing.Size(1265, 655);
            this.dataGridView1.TabIndex = 0;
            this.dataGridView1.CellContentClick += new System.Windows.Forms.DataGridViewCellEventHandler(this.dataGridView1_CellContentClick);
            // 
            // Conteudo
            // 
            this.Conteudo.FillWeight = 450F;
            this.Conteudo.HeaderText = "Conteudo";
            this.Conteudo.Name = "Conteudo";
            this.Conteudo.ReadOnly = true;
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
            // 
            // PROC_WSD
            // 
            this.PROC_WSD.FillWeight = 300F;
            this.PROC_WSD.HeaderText = "PROC. WSD";
            this.PROC_WSD.Name = "PROC_WSD";
            this.PROC_WSD.ReadOnly = true;
            // 
            // PROC_WPTGU
            // 
            this.PROC_WPTGU.FillWeight = 300F;
            this.PROC_WPTGU.HeaderText = "PROC. WPTGU";
            this.PROC_WPTGU.Name = "PROC_WPTGU";
            this.PROC_WPTGU.ReadOnly = true;
            // 
            // panelNormas
            // 
            this.panelNormas.Dock = System.Windows.Forms.DockStyle.Fill;
            this.panelNormas.Location = new System.Drawing.Point(0, 0);
            this.panelNormas.Name = "panelNormas";
            this.panelNormas.Size = new System.Drawing.Size(1271, 671);
            this.panelNormas.TabIndex = 1;
            this.panelNormas.Visible = false;
            // 
            // dataGridViewNormas
            // 
            this.dataGridViewNormas = new System.Windows.Forms.DataGridView();
            this.dataGridViewNormas.AllowUserToAddRows = false;
            this.dataGridViewNormas.AllowUserToDeleteRows = false;
            this.dataGridViewNormas.AllowUserToResizeRows = false;
            this.dataGridViewNormas.AutoSizeColumnsMode = System.Windows.Forms.DataGridViewAutoSizeColumnsMode.Fill;
            this.dataGridViewNormas.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dataGridViewNormas.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.Conteudo_N,
            this.Pagina_N,
            this.Processo_LEONI_N,
            this.PROC_WSD_N,
            this.PROC_WPTGU_N});
            this.dataGridViewNormas.Dock = System.Windows.Forms.DockStyle.Fill;
            this.dataGridViewNormas.Name = "dataGridViewNormas";
            this.dataGridViewNormas.ReadOnly = true;
            this.dataGridViewNormas.RowHeadersVisible = false;
            this.dataGridViewNormas.SelectionMode = System.Windows.Forms.DataGridViewSelectionMode.FullRowSelect;
            this.panelNormas.Controls.Add(this.dataGridViewNormas);
            // 
            // panelRequisitos
            // 
            this.panelRequisitos.Dock = System.Windows.Forms.DockStyle.Fill;
            this.panelRequisitos.Location = new System.Drawing.Point(0, 0);
            this.panelRequisitos.Name = "panelRequisitos";
            this.panelRequisitos.Size = new System.Drawing.Size(1271, 671);
            this.panelRequisitos.TabIndex = 2;
            this.panelRequisitos.Visible = false;
            // 
            // dataGridViewRequisitos
            // 
            this.dataGridViewRequisitos = new System.Windows.Forms.DataGridView();
            this.dataGridViewRequisitos.AllowUserToAddRows = false;
            this.dataGridViewRequisitos.AllowUserToDeleteRows = false;
            this.dataGridViewRequisitos.AllowUserToResizeRows = false;
            this.dataGridViewRequisitos.AutoSizeColumnsMode = System.Windows.Forms.DataGridViewAutoSizeColumnsMode.Fill;
            this.dataGridViewRequisitos.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dataGridViewRequisitos.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.Conteudo_R,
            this.Pagina_R,
            this.Processo_LEONI_R,
            this.PROC_WSD_R,
            this.PROC_WPTGU_R});
            this.dataGridViewRequisitos.Dock = System.Windows.Forms.DockStyle.Fill;
            this.dataGridViewRequisitos.Name = "dataGridViewRequisitos";
            this.dataGridViewRequisitos.ReadOnly = true;
            this.dataGridViewRequisitos.RowHeadersVisible = false;
            this.dataGridViewRequisitos.SelectionMode = System.Windows.Forms.DataGridViewSelectionMode.FullRowSelect;
            this.panelRequisitos.Controls.Add(this.dataGridViewRequisitos);
            // 
            // panelInstrucoes
            // 
            this.panelInstrucoes.Dock = System.Windows.Forms.DockStyle.Fill;
            this.panelInstrucoes.Location = new System.Drawing.Point(0, 0);
            this.panelInstrucoes.Name = "panelInstrucoes";
            this.panelInstrucoes.Size = new System.Drawing.Size(1271, 671);
            this.panelInstrucoes.TabIndex = 3;
            this.panelInstrucoes.Visible = false;
            // 
            // dataGridViewInstrucoes
            // 
            this.dataGridViewInstrucoes = new System.Windows.Forms.DataGridView();
            this.dataGridViewInstrucoes.AllowUserToAddRows = false;
            this.dataGridViewInstrucoes.AllowUserToDeleteRows = false;
            this.dataGridViewInstrucoes.AllowUserToResizeRows = false;
            this.dataGridViewInstrucoes.AutoSizeColumnsMode = System.Windows.Forms.DataGridViewAutoSizeColumnsMode.Fill;
            this.dataGridViewInstrucoes.ColumnHeadersHeightSizeMode = System.Windows.Forms.DataGridViewColumnHeadersHeightSizeMode.AutoSize;
            this.dataGridViewInstrucoes.Columns.AddRange(new System.Windows.Forms.DataGridViewColumn[] {
            this.Conteudo_I,
            this.Pagina_I,
            this.Processo_LEONI_I,
            this.PROC_WSD_I,
            this.PROC_WPTGU_I});
            this.dataGridViewInstrucoes.Dock = System.Windows.Forms.DockStyle.Fill;
            this.dataGridViewInstrucoes.Name = "dataGridViewInstrucoes";
            this.dataGridViewInstrucoes.ReadOnly = true;
            this.dataGridViewInstrucoes.RowHeadersVisible = false;
            this.dataGridViewInstrucoes.SelectionMode = System.Windows.Forms.DataGridViewSelectionMode.FullRowSelect;
            this.panelInstrucoes.Controls.Add(this.dataGridViewInstrucoes);
            // 
            // statusStrip1
            // 
            this.statusStrip1.Items.AddRange(new System.Windows.Forms.ToolStripItem[] {
            this.toolStripStatusLabel1});
            this.statusStrip1.Location = new System.Drawing.Point(0, 714);
            this.statusStrip1.Name = "statusStrip1";
            this.statusStrip1.Size = new System.Drawing.Size(1503, 22);
            this.statusStrip1.TabIndex = 2;
            // 
            // toolStripStatusLabel1
            // 
            this.toolStripStatusLabel1.Name = "toolStripStatusLabel1";
            this.toolStripStatusLabel1.Size = new System.Drawing.Size(39, 17);
            this.toolStripStatusLabel1.Text = "Ready";
            // 
            // label1
            // 
            this.label1.AutoSize = true;
            this.label1.Font = new System.Drawing.Font("Segoe UI", 11.25F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(0)));
            this.label1.Location = new System.Drawing.Point(12, 42);
            this.label1.Name = "label1";
            this.label1.Size = new System.Drawing.Size(79, 25);
            this.label1.TabIndex = 2;
            this.label1.Text = "Cliente:";
            this.label1.Click += new System.EventHandler(this.label1_Click);
            // 
            // label2
            // 
            this.label2.AutoSize = true;
            this.label2.Font = new System.Drawing.Font("Segoe UI", 11.25F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(0)));
            this.label2.Location = new System.Drawing.Point(312, 42);
            this.label2.Name = "label2";
            this.label2.Size = new System.Drawing.Size(66, 25);
            this.label2.TabIndex = 3;
            this.label2.Text = "Titulo:";
            // 
            // button1
            // 
            this.button1.FlatStyle = System.Windows.Forms.FlatStyle.System;
            this.button1.Location = new System.Drawing.Point(15, 7);
            this.button1.Name = "button1";
            this.button1.Size = new System.Drawing.Size(110, 32);
            this.button1.TabIndex = 4;
            this.button1.Text = "Mudar Projeto";
            this.button1.UseVisualStyleBackColor = true;
            // 
            // button2
            // 
            this.button2.FlatStyle = System.Windows.Forms.FlatStyle.System;
            this.button2.Location = new System.Drawing.Point(133, 7);
            this.button2.Name = "button2";
            this.button2.Size = new System.Drawing.Size(120, 32);
            this.button2.TabIndex = 5;
            this.button2.Text = "Atualizar Matriz";
            this.button2.UseVisualStyleBackColor = true;
            this.button2.Click += new System.EventHandler(this.button2_Click);
            // 
            // Form1
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(7F, 15F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.ClientSize = new System.Drawing.Size(1503, 736);
            this.Controls.Add(this.splitContainerMain);
            this.Controls.Add(this.toolStrip1);
            this.Controls.Add(this.statusStrip1);
            this.Font = new System.Drawing.Font("Segoe UI", 9F, System.Drawing.FontStyle.Regular, System.Drawing.GraphicsUnit.Point, ((byte)(0)));
            this.Name = "Form1";
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterScreen;
            this.Text = "ComplyAI — Matrix";
            this.toolStrip1.ResumeLayout(false);
            this.toolStrip1.PerformLayout();
            this.splitContainerMain.Panel1.ResumeLayout(false);
            this.splitContainerMain.Panel2.ResumeLayout(false);
            ((System.ComponentModel.ISupportInitialize)(this.splitContainerMain)).EndInit();
            this.splitContainerMain.ResumeLayout(false);
            this.panelMatrix.ResumeLayout(false);
            this.panelNormas.ResumeLayout(false);
            this.panelRequisitos.ResumeLayout(false);
            this.panelInstrucoes.ResumeLayout(false);
            ((System.ComponentModel.ISupportInitialize)(this.dataGridView1)).EndInit();
            this.statusStrip1.ResumeLayout(false);
            this.statusStrip1.PerformLayout();
            this.ResumeLayout(false);
            this.PerformLayout();

        }

        #endregion
        private System.Windows.Forms.ToolStrip toolStrip1;
        private System.Windows.Forms.ToolStripComboBox toolStripComboBoxProject;
        private System.Windows.Forms.ToolStripTextBox toolStripTextBoxSearch;
        private System.Windows.Forms.ToolStripButton toolStripButtonRefresh;
        private System.Windows.Forms.SplitContainer splitContainerMain;
        private System.Windows.Forms.ListBox listBoxNav;
        private System.Windows.Forms.Panel panelMatrix;
        private System.Windows.Forms.Panel panelNormas;
        private System.Windows.Forms.Panel panelRequisitos;
        private System.Windows.Forms.Panel panelInstrucoes;
        private System.Windows.Forms.DataGridView dataGridView1;
        private System.Windows.Forms.DataGridView dataGridViewNormas;
        private System.Windows.Forms.DataGridView dataGridViewRequisitos;
        private System.Windows.Forms.DataGridView dataGridViewInstrucoes;
        private System.Windows.Forms.DataGridViewTextBoxColumn Conteudo;
        private System.Windows.Forms.DataGridViewTextBoxColumn Página;
        private System.Windows.Forms.DataGridViewTextBoxColumn Processo_LEONI;
        private System.Windows.Forms.DataGridViewTextBoxColumn PROC_WSD;
        private System.Windows.Forms.DataGridViewTextBoxColumn PROC_WPTGU;
        private System.Windows.Forms.DataGridViewTextBoxColumn Conteudo_N;
        private System.Windows.Forms.DataGridViewTextBoxColumn Pagina_N;
        private System.Windows.Forms.DataGridViewTextBoxColumn Processo_LEONI_N;
        private System.Windows.Forms.DataGridViewTextBoxColumn PROC_WSD_N;
        private System.Windows.Forms.DataGridViewTextBoxColumn PROC_WPTGU_N;
        private System.Windows.Forms.DataGridViewTextBoxColumn Conteudo_R;
        private System.Windows.Forms.DataGridViewTextBoxColumn Pagina_R;
        private System.Windows.Forms.DataGridViewTextBoxColumn Processo_LEONI_R;
        private System.Windows.Forms.DataGridViewTextBoxColumn PROC_WSD_R;
        private System.Windows.Forms.DataGridViewTextBoxColumn PROC_WPTGU_R;
        private System.Windows.Forms.DataGridViewTextBoxColumn Conteudo_I;
        private System.Windows.Forms.DataGridViewTextBoxColumn Pagina_I;
        private System.Windows.Forms.DataGridViewTextBoxColumn Processo_LEONI_I;
        private System.Windows.Forms.DataGridViewTextBoxColumn PROC_WSD_I;
        private System.Windows.Forms.DataGridViewTextBoxColumn PROC_WPTGU_I;
        private System.Windows.Forms.StatusStrip statusStrip1;
        private System.Windows.Forms.ToolStripStatusLabel toolStripStatusLabel1;
        private System.Windows.Forms.Label label1;
        private System.Windows.Forms.Label label2;
        private System.Windows.Forms.Button button1;
        private System.Windows.Forms.Button button2;
    }
}

