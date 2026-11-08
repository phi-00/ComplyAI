
using System;

namespace ComplyAI
{
    partial class FormInicio
    {
        private System.ComponentModel.IContainer components = null;

        private System.Windows.Forms.Panel barraSuperior;
        private System.Windows.Forms.Button btnMinimizar;
        private System.Windows.Forms.Button btnMaximizar;
        private System.Windows.Forms.Button btnFechar;
        private System.Windows.Forms.PictureBox pbLogo;
        private System.Windows.Forms.Button btnVerProjetos;
        private System.Windows.Forms.Label lblEstadoLigacao;
        private System.Windows.Forms.Label lblProjetos;
        private System.Windows.Forms.ListBox lstProjetos;

        protected override void Dispose(bool disposing)
        {
            if (disposing && (components != null))
            {
                components.Dispose();
            }

            base.Dispose(disposing);
        }

        private void InitializeComponent()
        {
            this.barraSuperior = new System.Windows.Forms.Panel();
            this.btnMinimizar = new System.Windows.Forms.Button();
            this.btnMaximizar = new System.Windows.Forms.Button();
            this.btnFechar = new System.Windows.Forms.Button();
            this.pbLogo = new System.Windows.Forms.PictureBox();
            this.btnVerProjetos = new System.Windows.Forms.Button();
            this.lblEstadoLigacao = new System.Windows.Forms.Label();
            this.lblProjetos = new System.Windows.Forms.Label();
            this.lstProjetos = new System.Windows.Forms.ListBox();
            this.barraSuperior.SuspendLayout();
            ((System.ComponentModel.ISupportInitialize)(this.pbLogo)).BeginInit();
            this.SuspendLayout();
            // 
            // barraSuperior
            // 
            this.barraSuperior.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(0)))), ((int)(((byte)(61)))), ((int)(((byte)(136)))));
            this.barraSuperior.Controls.Add(this.btnMinimizar);
            this.barraSuperior.Controls.Add(this.btnMaximizar);
            this.barraSuperior.Controls.Add(this.btnFechar);
            this.barraSuperior.Dock = System.Windows.Forms.DockStyle.Top;
            this.barraSuperior.Location = new System.Drawing.Point(0, 0);
            this.barraSuperior.Name = "barraSuperior";
            this.barraSuperior.Size = new System.Drawing.Size(900, 42);
            this.barraSuperior.TabIndex = 0;
            this.barraSuperior.Paint += new System.Windows.Forms.PaintEventHandler(this.barraSuperior_Paint);
            this.barraSuperior.MouseDown += new System.Windows.Forms.MouseEventHandler(this.ArrastarFormulario);
            // 
            // btnMinimizar
            // 
            this.btnMinimizar.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnMinimizar.BackColor = System.Drawing.Color.FromArgb(0, 61, 136);
            this.btnMinimizar.FlatAppearance.BorderSize = 0;
            this.btnMinimizar.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.btnMinimizar.Font = new System.Drawing.Font("Segoe UI", 10F, System.Drawing.FontStyle.Bold);
            this.btnMinimizar.ForeColor = System.Drawing.Color.White;
            this.btnMinimizar.Location = new System.Drawing.Point(774, 0);
            this.btnMinimizar.Name = "btnMinimizar";
            this.btnMinimizar.Size = new System.Drawing.Size(42, 42);
            this.btnMinimizar.TabIndex = 0;
            this.btnMinimizar.Image = global::ComplyAI.Properties.Resources.minus;
            this.btnMinimizar.UseVisualStyleBackColor = false;
            this.btnMinimizar.Click += new System.EventHandler(this.btnMinimizar_Click);
            // 
            // btnMaximizar
            // 
            this.btnMaximizar.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnMaximizar.BackColor = System.Drawing.Color.FromArgb(0, 61, 136);
            this.btnMaximizar.FlatAppearance.BorderSize = 0;
            this.btnMaximizar.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.btnMaximizar.Font = new System.Drawing.Font("Segoe UI", 10F, System.Drawing.FontStyle.Bold);
            this.btnMaximizar.ForeColor = System.Drawing.Color.White;
            this.btnMaximizar.Location = new System.Drawing.Point(816, 0);
            this.btnMaximizar.Name = "btnMaximizar";
            this.btnMaximizar.Size = new System.Drawing.Size(42, 42);
            this.btnMaximizar.TabIndex = 2;
            this.btnMaximizar.Image = global::ComplyAI.Properties.Resources.copy_1_;
            this.btnMaximizar.UseVisualStyleBackColor = false;
            this.btnMaximizar.Click += new System.EventHandler(this.btnMaximizar_Click);
            // 
            // btnFechar
            // 
            this.btnFechar.Anchor = ((System.Windows.Forms.AnchorStyles)((System.Windows.Forms.AnchorStyles.Top | System.Windows.Forms.AnchorStyles.Right)));
            this.btnFechar.BackColor = System.Drawing.Color.FromArgb(0, 61, 136);
            this.btnFechar.FlatAppearance.BorderSize = 0;
            this.btnFechar.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.btnFechar.Font = new System.Drawing.Font("Segoe UI", 18F);
            this.btnFechar.ForeColor = System.Drawing.Color.White;
            this.btnFechar.Location = new System.Drawing.Point(858, 0);
            this.btnFechar.Name = "btnFechar";
            this.btnFechar.Size = new System.Drawing.Size(42, 42);
            this.btnFechar.TabIndex = 1;
            this.btnFechar.Image = global::ComplyAI.Properties.Resources.cross_4_;
            this.btnFechar.UseVisualStyleBackColor = false;
            this.btnFechar.Click += new System.EventHandler(this.btnFechar_Click);
            // 
            // pbLogo
            // 
            this.pbLogo.BackColor = System.Drawing.Color.Transparent;
            this.pbLogo.Image = global::ComplyAI.Properties.Resources.LeoniLogo;
            this.pbLogo.Location = new System.Drawing.Point(29, 368);
            this.pbLogo.Name = "pbLogo";
            this.pbLogo.Size = new System.Drawing.Size(415, 161);
            this.pbLogo.SizeMode = System.Windows.Forms.PictureBoxSizeMode.Zoom;
            this.pbLogo.TabIndex = 1;
            this.pbLogo.TabStop = false;
            this.pbLogo.Click += new System.EventHandler(this.pbLogo_Click);
            // 
            // btnVerProjetos
            // 
            this.btnVerProjetos.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(0)))), ((int)(((byte)(61)))), ((int)(((byte)(136)))));
            this.btnVerProjetos.Cursor = System.Windows.Forms.Cursors.Hand;
            this.btnVerProjetos.FlatAppearance.BorderSize = 0;
            this.btnVerProjetos.FlatStyle = System.Windows.Forms.FlatStyle.Flat;
            this.btnVerProjetos.Font = new System.Drawing.Font("Segoe UI", 10F, System.Drawing.FontStyle.Bold);
            this.btnVerProjetos.ForeColor = System.Drawing.Color.White;
            this.btnVerProjetos.Location = new System.Drawing.Point(617, 83);
            this.btnVerProjetos.Name = "btnVerProjetos";
            this.btnVerProjetos.Size = new System.Drawing.Size(193, 32);
            this.btnVerProjetos.TabIndex = 2;
            this.btnVerProjetos.Text = "Ver lista de projetos";
            this.btnVerProjetos.UseVisualStyleBackColor = false;
            this.btnVerProjetos.Click += new System.EventHandler(this.btnVerProjetos_Click);
            // 
            // lblEstadoLigacao
            // 
            this.lblEstadoLigacao.Font = new System.Drawing.Font("Segoe UI", 9F);
            this.lblEstadoLigacao.ForeColor = System.Drawing.Color.FromArgb(((int)(((byte)(100)))), ((int)(((byte)(116)))), ((int)(((byte)(139)))));
            this.lblEstadoLigacao.Location = new System.Drawing.Point(259, 58);
            this.lblEstadoLigacao.Name = "lblEstadoLigacao";
            this.lblEstadoLigacao.Size = new System.Drawing.Size(400, 25);
            this.lblEstadoLigacao.TabIndex = 3;
            this.lblEstadoLigacao.Text = "A verificar ligação ao servidor...";
            this.lblEstadoLigacao.TextAlign = System.Drawing.ContentAlignment.MiddleCenter;
            // 
            // lblProjetos
            // 
            this.lblProjetos.Font = new System.Drawing.Font("Segoe UI", 11F, System.Drawing.FontStyle.Bold);
            this.lblProjetos.ForeColor = System.Drawing.Color.FromArgb(((int)(((byte)(0)))), ((int)(((byte)(61)))), ((int)(((byte)(136)))));
            this.lblProjetos.Location = new System.Drawing.Point(558, 374);
            this.lblProjetos.Name = "lblProjetos";
            this.lblProjetos.Size = new System.Drawing.Size(300, 25);
            this.lblProjetos.TabIndex = 0;
            this.lblProjetos.Text = "Projetos disponíveis";
            this.lblProjetos.TextAlign = System.Drawing.ContentAlignment.MiddleLeft;
            // 
            // lstProjetos
            // 
            this.lstProjetos.BorderStyle = System.Windows.Forms.BorderStyle.FixedSingle;
            this.lstProjetos.Font = new System.Drawing.Font("Segoe UI", 10F);
            this.lstProjetos.IntegralHeight = false;
            this.lstProjetos.ItemHeight = 17;
            this.lstProjetos.Location = new System.Drawing.Point(558, 121);
            this.lstProjetos.Name = "lstProjetos";
            this.lstProjetos.Size = new System.Drawing.Size(300, 250);
            this.lstProjetos.TabIndex = 1;
            this.lstProjetos.SelectedIndexChanged += new System.EventHandler(this.lstProjetos_SelectedIndexChanged);
            // 
            // FormInicio
            // 
            this.AutoScaleDimensions = new System.Drawing.SizeF(7F, 15F);
            this.AutoScaleMode = System.Windows.Forms.AutoScaleMode.Font;
            this.BackColor = System.Drawing.Color.FromArgb(((int)(((byte)(241)))), ((int)(((byte)(245)))), ((int)(((byte)(249)))));
            this.ClientSize = new System.Drawing.Size(900, 550);
            this.Controls.Add(this.lblProjetos);
            this.Controls.Add(this.lstProjetos);
            this.Controls.Add(this.lblEstadoLigacao);
            this.Controls.Add(this.btnVerProjetos);
            this.Controls.Add(this.pbLogo);
            this.Controls.Add(this.barraSuperior);
            this.Font = new System.Drawing.Font("Segoe UI", 9F);
            this.FormBorderStyle = System.Windows.Forms.FormBorderStyle.None;
            this.MinimumSize = new System.Drawing.Size(700, 450);
            this.Name = "FormInicio";
            this.StartPosition = System.Windows.Forms.FormStartPosition.CenterScreen;
            this.Text = "ComplyAI";
            this.Load += new System.EventHandler(this.FormInicio_Load);
            this.barraSuperior.ResumeLayout(false);
            ((System.ComponentModel.ISupportInitialize)(this.pbLogo)).EndInit();
            this.ResumeLayout(false);

        }
    }
}
