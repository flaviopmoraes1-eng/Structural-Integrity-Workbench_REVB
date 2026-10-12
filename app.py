import streamlit as st
from PIL import Image
import os
import plotly.graph_objects as go
import numpy as np
import struct

# Configuração da página
st.set_page_config(page_title="Structural Integrity Workbench", layout="wide")

# Inicializar session_state
if "api_executada" not in st.session_state:
    st.session_state.api_executada = False

st.title("Structural Integrity Workbench")

# Função para formatar espaçamento entre parágrafos
def format_spacing(text):
    """Formata espaçamento simples entre parágrafos"""
    # Dividir por linhas em branco duplas e adicionar <br><br>
    paragrafos = [p.strip() for p in text.split('\n\n') if p.strip()]
    return '<br><br>'.join(paragrafos)

# Função para carregar arquivo STL
def load_stl_file(filepath):
    """Carrega um arquivo STL (ASCII ou binário) e retorna vertices, faces e cores"""
    vertices = []
    faces = []
    face_materials = []
    face_colors = []
    
    try:
        with open(filepath, 'rb') as f:
            # Verificar se é STL binário ou ASCII
            header = f.read(5)
            
            if header.lower() == b'solid':
                # STL ASCII
                f.close()
                with open(filepath, 'r') as f:
                    for line in f:
                        parts = line.strip().split()
                        if len(parts) >= 4:
                            if parts[0] == 'vertex':
                                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
                            elif parts[0] == 'endfacet':
                                if len(vertices) % 3 == 0 and len(vertices) > 0:
                                    v_count = len(vertices)
                                    faces.append([v_count - 3, v_count - 2, v_count - 1])
                                    face_materials.append('default')
            else:
                # STL Binário
                f.seek(0)
                f.read(80)  # Header
                num_triangles = struct.unpack('I', f.read(4))[0]
                
                for _ in range(num_triangles):
                    f.read(12)  # Normal vector (skip)
                    # Ler os 3 vértices
                    v1 = struct.unpack('fff', f.read(12))
                    v2 = struct.unpack('fff', f.read(12))
                    v3 = struct.unpack('fff', f.read(12))
                    
                    vertices.append(list(v1))
                    vertices.append(list(v2))
                    vertices.append(list(v3))
                    
                    idx = len(vertices) - 3
                    faces.append([idx, idx + 1, idx + 2])
                    
                    # Tentar ler cor do atributo (formato: RGB em 5 bits cada = 16 bits)
                    attr_bytes = f.read(2)
                    color = [0.65, 0.68, 0.72]  # cor padrão
                    
                    if len(attr_bytes) == 2:
                        attr_value = struct.unpack('H', attr_bytes)[0]
                        # Verificar se tem cor (bit 15 = 1)
                        if attr_value & 0x8000:
                            # Extrair RGB (5 bits cada)
                            r = ((attr_value >> 10) & 0x1F) / 31.0
                            g = ((attr_value >> 5) & 0x1F) / 31.0
                            b = (attr_value & 0x1F) / 31.0
                            color = [r, g, b]
                    
                    face_colors.append(color)
                    # Usar cor como nome do material
                    mat_name = f"color_{len(face_colors)}"
                    face_materials.append(mat_name)
    except Exception as e:
        st.error(f"Erro ao ler arquivo STL: {e}")
        return np.array([]), [], [], {}
    
    # Tentar carregar material de arquivo .mtl associado
    mtl_filepath = filepath.replace('.stl', '.mtl')
    materials = load_mtl_file(mtl_filepath) if os.path.exists(mtl_filepath) else {}
    
    # Se não houver arquivo MTL, criar materiais a partir das cores encontradas
    if not materials:
        if face_colors:
            materials = {}
            for i, color in enumerate(face_colors):
                materials[f"color_{i+1}"] = {'Kd': color, 'd': 1.0}
        else:
            materials = {'default': {'Kd': [0.65, 0.68, 0.72], 'd': 1.0}}
    
    return np.array(vertices), faces, face_materials, materials

# Função para carregar arquivo MTL
def load_mtl_file(filepath):
    """Carrega informações de material do arquivo MTL"""
    materials = {}
    current_material = None
    
    if not os.path.exists(filepath):
        return materials
    
    with open(filepath, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if not parts or parts[0].startswith('#'):
                continue
            
            if parts[0] == 'newmtl':
                current_material = parts[1]
                materials[current_material] = {
                    'Kd': [0.8, 0.8, 0.8],  # cor padrão (branco)
                    'Ka': [0.2, 0.2, 0.2],  # cor ambiente
                    'Ks': [1.0, 1.0, 1.0],  # cor especular
                    'd': 1.0  # opacidade
                }
            elif parts[0] == 'Kd' and current_material:  # Cor difusa (cor principal)
                materials[current_material]['Kd'] = [float(parts[1]), float(parts[2]), float(parts[3])]
            elif parts[0] == 'Ka' and current_material:  # Cor ambiente
                materials[current_material]['Ka'] = [float(parts[1]), float(parts[2]), float(parts[3])]
            elif parts[0] == 'Ks' and current_material:  # Cor especular
                materials[current_material]['Ks'] = [float(parts[1]), float(parts[2]), float(parts[3])]
            elif parts[0] == 'd' and current_material:  # Opacidade
                materials[current_material]['d'] = float(parts[1])
            elif parts[0] == 'Tr' and current_material:  # Transparência (inverso de opacidade)
                materials[current_material]['d'] = 1.0 - float(parts[1])
    
    return materials

# Função para carregar dados de tensão e mapear para cores
def load_stress_data(stress_filepath):
    """Carrega dados de tensão de von-Mises e retorna lista de cores e valores de tensão"""
    stress_values = []
    
    if not os.path.exists(stress_filepath):
        return [], []
    
    try:
        with open(stress_filepath, 'r', encoding='utf-8') as f:
            lines = f.readlines()
            # Pular cabeçalho
            for line in lines[1:]:
                parts = line.strip().split('\t')
                if len(parts) >= 2:
                    try:
                        # Converter valor de tensão (pode usar vírgula como separador decimal)
                        stress_str = parts[1].replace(',', '.')
                        stress = float(stress_str)
                        stress_values.append(stress)
                    except:
                        pass
    except Exception as e:
        st.warning(f"Erro ao carregar dados de tensão: {e}")
        return [], []
    
    if not stress_values:
        return [], []
    
    # Normalizar valores (0-1)
    min_stress = min(stress_values)
    max_stress = max(stress_values)
    
    if min_stress == max_stress:
        normalized = [0.5] * len(stress_values)
    else:
        normalized = [(s - min_stress) / (max_stress - min_stress) for s in stress_values]
    
    # Mapear para cores com gradiente: Azul → Laranja → Vermelho
    colors = []
    for norm_val in normalized:
        # Gradiente em 5 pontos:
        # 0.0 → Azul (0, 0, 1)
        # 0.25 → Ciano (0, 1, 1)
        # 0.5 → Amarelo (1, 1, 0)
        # 0.75 → Laranja (1, 0.5, 0)
        # 1.0 → Vermelho (1, 0, 0)
        
        if norm_val < 0.25:
            # Azul → Ciano
            t = norm_val / 0.25
            r = 0
            g = t
            b = 1
        elif norm_val < 0.5:
            # Ciano → Amarelo
            t = (norm_val - 0.25) / 0.25
            r = t
            g = 1
            b = 1 - t
        elif norm_val < 0.75:
            # Amarelo → Laranja
            t = (norm_val - 0.5) / 0.25
            r = 1
            g = 1 - (t * 0.5)
            b = 0
        else:
            # Laranja → Vermelho
            t = (norm_val - 0.75) / 0.25
            r = 1
            g = 0.5 - (t * 0.5)
            b = 0
        
        colors.append([r, g, b])
    
    return colors, stress_values

# Função para carregar arquivo OBJ
def load_obj_file(filepath):
    """Carrega um arquivo OBJ e retorna vertices, faces e cores"""
    vertices = []
    faces = []
    face_materials = []
    materials = {}
    current_material = None
    
    # Carregar arquivo MTL primeiro
    mtl_filepath = filepath.replace('.obj', '.mtl')
    materials = load_mtl_file(mtl_filepath)
    
    with open(filepath, 'r') as f:
        for line in f:
            parts = line.strip().split()
            if not parts or parts[0].startswith('#'):
                continue
            
            if parts[0] == 'v':
                vertices.append([float(parts[1]), float(parts[2]), float(parts[3])])
            elif parts[0] == 'usemtl':
                current_material = parts[1]
            elif parts[0] == 'f':
                face = []
                for part in parts[1:]:
                    vertex_index = int(part.split('/')[0]) - 1
                    face.append(vertex_index)
                faces.append(face)
                face_materials.append(current_material)
    
    return np.array(vertices), faces, face_materials, materials

# Função para criar visualização 3D com Plotly
def plot_3d_model(vertices, faces, face_materials, materials, stress_values=None):
    """Cria um gráfico 3D interativo usando Plotly com cores originais"""
    x = vertices[:, 0]
    y = vertices[:, 1]
    z = vertices[:, 2]
    
    # Se não houver informações de material, usar cor de aço industrial
    if not materials:
        materials = {'default': {'Kd': [0.65, 0.68, 0.72], 'd': 1.0}}
        face_materials = ['default'] * len(faces)
    
    # Criar lista de cores por face
    colors = []
    alphas = []
    for mat_name in face_materials:
        if mat_name in materials:
            color_rgb = materials[mat_name]['Kd']
            alpha = materials[mat_name]['d']
        else:
            color_rgb = [0.65, 0.68, 0.72]  # aço industrial
            alpha = 1.0
        
        # Converter RGB (0-1) para formato Plotly (0-255)
        colors.append(f'rgba({int(color_rgb[0]*255)}, {int(color_rgb[1]*255)}, {int(color_rgb[2]*255)}, {alpha})')
        alphas.append(alpha)
    
    i_indices = []
    j_indices = []
    k_indices = []
    face_colors = []
    hover_texts = []
    
    # Extrair arestas do modelo
    edges = set()
    for idx, face in enumerate(faces):
        if len(face) >= 3:
            i_indices.append(face[0])
            j_indices.append(face[1])
            k_indices.append(face[2])
            face_colors.append(colors[idx])
            
            # Adicionar hovertext com tensão (se disponível)
            if stress_values and idx < len(stress_values):
                hover_text = f"Tensão: {stress_values[idx]:.2f} MPa"
            else:
                hover_text = f"Face {idx}"
            hover_texts.append(hover_text)
            
            # Adicionar arestas (garantir ordem para evitar duplicatas)
            edges.add((min(face[0], face[1]), max(face[0], face[1])))
            edges.add((min(face[1], face[2]), max(face[1], face[2])))
            edges.add((min(face[2], face[0]), max(face[2], face[0])))
    
    # Criar linhas para as arestas
    edge_x = []
    edge_y = []
    edge_z = []
    
    for edge in edges:
        v1_idx, v2_idx = edge
        edge_x.extend([x[v1_idx], x[v2_idx], None])
        edge_y.extend([y[v1_idx], y[v2_idx], None])
        edge_z.extend([z[v1_idx], z[v2_idx], None])
    
    # Criar figura com mesh e arestas
    fig = go.Figure()
    
    # Adicionar mesh 3D
    fig.add_trace(go.Mesh3d(
        x=x, y=y, z=z,
        i=i_indices,
        j=j_indices,
        k=k_indices,
        facecolor=face_colors,
        hovertext=hover_texts if hover_texts else None,
        hoverinfo='text' if hover_texts else 'skip',
        opacity=1.0,
        name='Modelo 3D',
        showscale=False,
        flatshading=False
    ))
    
    # Adicionar linhas das arestas em preto
    fig.add_trace(go.Scatter3d(
        x=edge_x,
        y=edge_y,
        z=edge_z,
        mode='lines',
        line=dict(color='black', width=1),
        name='Arestas',
        hoverinfo='skip',
        showlegend=False
    ))
    
    fig.update_layout(
        scene=dict(
            xaxis_title="X",
            yaxis_title="Y",
            zaxis_title="Z",
            aspectmode="data",
            bgcolor="rgba(255, 255, 255, 1)",
            xaxis=dict(showgrid=True, gridwidth=1, gridcolor="rgba(200, 200, 200, 0.5)"),
            yaxis=dict(showgrid=True, gridwidth=1, gridcolor="rgba(200, 200, 200, 0.5)"),
            zaxis=dict(showgrid=True, gridwidth=1, gridcolor="rgba(200, 200, 200, 0.5)"),
            camera=dict(
                eye=dict(x=1.5, y=1.5, z=1.3)
            )
        ),
        width=800,
        height=800,
        showlegend=False,
        paper_bgcolor="rgba(255, 255, 255, 1)",
        font=dict(color="rgba(0, 0, 0, 1)")
    )
    
    return fig

# Lista de equipamentos disponíveis
equipamentos = ["VMSTRESS", "V-45673D", "F-2217", "V-5021", "pipe"]

# Caixa de combinação para seleção do equipamento
equipamento_selecionado = st.selectbox(
    "Escolha um equipamento:",
    equipamentos,
    index=0
)

# Criar 3 colunas
col1, col2, col3 = st.columns(3)

# COLUNA 1: Imagem ou Modelo 3D
with col1:
    # Caminho da imagem ou modelo 3D
    diretorio_atual = os.path.dirname(os.path.abspath(__file__))
    caminho_imagem = os.path.join(diretorio_atual, f"{equipamento_selecionado}.png")
    caminho_modelo_3d = os.path.join(diretorio_atual, "file.stl")
    caminho_vmstress = os.path.join(diretorio_atual, "VMSTRESS_STL.stl")
    
    # Exibir a imagem ou modelo 3D
    if equipamento_selecionado == "V-45673D":
        if os.path.exists(caminho_modelo_3d):
            try:
                vertices, faces, face_materials, materials = load_stl_file(caminho_modelo_3d)
                fig = plot_3d_model(vertices, faces, face_materials, materials)
                st.plotly_chart(fig, width='stretch')
                st.caption("💡 Rotacione com mouse • Zoom com scroll")
            except Exception as e:
                st.error(f"Erro ao carregar o modelo 3D: {e}")
        else:
            st.error(f"Modelo 3D não encontrado")
    elif equipamento_selecionado == "VMSTRESS":
        if os.path.exists(caminho_vmstress):
            try:
                vertices, faces, face_materials, materials = load_stl_file(caminho_vmstress)
                
                # Carregar dados de tensão e aplicar cores
                stress_filepath = os.path.join(diretorio_atual, "VMSTRESS_texto.txt")
                stress_colors, stress_values = load_stress_data(stress_filepath)
                
                if stress_colors:
                    # Aplicar cores de tensão aos materiais
                    materials = {}
                    face_materials_new = []
                    
                    for i, color in enumerate(stress_colors):
                        mat_name = f"stress_{i}"
                        materials[mat_name] = {'Kd': color, 'd': 1.0}
                        face_materials_new.append(mat_name)
                    
                    # Se houver mais faces que cores, repetir as cores
                    while len(face_materials_new) < len(faces):
                        for i in range(len(stress_colors)):
                            if len(face_materials_new) < len(faces):
                                face_materials_new.append(f"stress_{i}")
                    
                    face_materials = face_materials_new[:len(faces)]
                
                fig = plot_3d_model(vertices, faces, face_materials, materials, stress_values)
                st.plotly_chart(fig, width='stretch')
                st.caption("💡 Rotacione com mouse • Zoom com scroll • Cores: Azul (baixa) → Amarelo → Laranja → Vermelho (alta tensão)")
            except Exception as e:
                st.error(f"Erro ao carregar o modelo 3D: {e}")
        else:
            st.error(f"Modelo 3D VMSTRESS não encontrado")
    elif equipamento_selecionado == "pipe":
        caminho_pipe = os.path.join(diretorio_atual, "pipe.stl")
        if os.path.exists(caminho_pipe):
            try:
                vertices, faces, face_materials, materials = load_stl_file(caminho_pipe)
                
                # Carregar dados de tensão e aplicar cores
                stress_filepath = os.path.join(diretorio_atual, "pipe.txt")
                stress_colors, stress_values = load_stress_data(stress_filepath)
                
                if stress_colors:
                    # Aplicar cores de tensão aos materiais
                    materials = {}
                    face_materials_new = []
                    
                    for i, color in enumerate(stress_colors):
                        mat_name = f"stress_{i}"
                        materials[mat_name] = {'Kd': color, 'd': 1.0}
                        face_materials_new.append(mat_name)
                    
                    # Se houver mais faces que cores, repetir as cores
                    while len(face_materials_new) < len(faces):
                        for i in range(len(stress_colors)):
                            if len(face_materials_new) < len(faces):
                                face_materials_new.append(f"stress_{i}")
                    
                    face_materials = face_materials_new[:len(faces)]
                
                fig = plot_3d_model(vertices, faces, face_materials, materials, stress_values)
                st.plotly_chart(fig, width='stretch')
                st.caption("💡 Rotacione com mouse • Zoom com scroll • Cores: Azul (baixa) → Amarelo → Laranja → Vermelho (alta tensão)")
            except Exception as e:
                st.error(f"Erro ao carregar o modelo 3D: {e}")
        else:
            st.error(f"Modelo 3D pipe não encontrado")
    else:
        if os.path.exists(caminho_imagem):
            imagen = Image.open(caminho_imagem)
            st.image(imagen, caption=f"Equipamento: {equipamento_selecionado}", use_column_width=True)
        else:
            st.error(f"Imagem não encontrada")
    
    # Botão Rodar API
    st.write("")
    if st.button("Rodar API-579 Part 9 N2", key="rodar_api_btn", width='stretch'):
        st.session_state.api_executada = True
    
    # Se o botão foi clicado, mostrar mensagem
    if st.session_state.get("api_executada", False):
        st.success("✓ API-579 Part 9 N2 executada com sucesso!")

# COLUNA 2: Informações de Solda
with col2:
    st.write("**Equipamento:** " + equipamento_selecionado)
    
    # Se a API foi executada, exibir imagem FAD e laudo lado a lado
    if st.session_state.get("api_executada", False):
        st.write("---")
        st.caption("Resultado FAD")
        
        # Criar sub-colunas para FAD e laudo
        fad_col, laudo_col = st.columns([1, 1])
        
        with fad_col:
            caminho_fad = os.path.join(diretorio_atual, "FAD.png")
            if os.path.exists(caminho_fad):
                imagen_fad = Image.open(caminho_fad)
                st.image(imagen_fad, width=350)
            else:
                st.error("FAD.png não encontrado")
            
            # Exibir Warnings
            st.write("")  # Espaço
            caminho_warnings = os.path.join(diretorio_atual, "Warnigs.txt")
            if os.path.exists(caminho_warnings):
                with open(caminho_warnings, 'r', encoding='utf-8') as f:
                    conteudo_warnings = f.read()
                # Formatar com primeira linha em negrito e espaçamento entre parágrafos
                lines_warnings = conteudo_warnings.split('\n')
                if lines_warnings:
                    first_line = f"<b>{lines_warnings[0]}</b>"
                    rest_content = "\n".join(lines_warnings[1:]).strip()
                    formatted_warnings = first_line + (f"<br><br>{format_spacing(rest_content)}" if rest_content else "")
                else:
                    formatted_warnings = conteudo_warnings
                st.markdown(f"""
                <div style="color: #000000; background-color: #fff3cd; padding: 15px; border-radius: 8px; border: 1px solid #ffc107; border-left: 4px solid #ff6b6b; font-family: Arial, sans-serif; white-space: pre-wrap; word-wrap: break-word; font-size: 12px; line-height: 1.4; max-height: 600px; overflow-y: auto; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                <b>⚠️ WARNINGS:</b><br>
                {formatted_warnings}
                </div>
                """, unsafe_allow_html=True)
        
        with laudo_col:
            # Adicionar botões em 2 linhas
            btn_col1, btn_col2 = st.columns(2)
            
            with btn_col1:
                if st.button("📄 Print Report"):
                    st.success("Report enviado para impressão!")
                
                if st.button("📊 Módulo de Fadiga"):
                    st.info("Módulo de Fadiga ativado!")
            
            with btn_col2:
                if st.button("⏱️ Módulo de Fluência"):
                    st.info("Módulo de Fluência ativado!")
                
                if st.button("🔧 Postular Defeitos"):
                    st.warning("Postulação de defeitos iniciada!")
            
            st.write("")  # Espaço
            
            # Exibir laudo
            caminho_laudo = os.path.join(diretorio_atual, "Laudo.txt")
            if os.path.exists(caminho_laudo):
                with open(caminho_laudo, 'r', encoding='utf-8') as f:
                    conteudo_laudo = f.read()
                # Formatar com primeira linha em negrito e espaçamento entre parágrafos
                lines_laudo = conteudo_laudo.split('\n')
                if lines_laudo:
                    first_line = f"<b>{lines_laudo[0]}</b>"
                    rest_content = "\n".join(lines_laudo[1:]).strip()
                    formatted_laudo = first_line + (f"<br><br>{format_spacing(rest_content)}" if rest_content else "")
                else:
                    formatted_laudo = conteudo_laudo
                st.markdown(f"""
                <div style="color: #000000; background-color: #f5f5f5; padding: 20px; border-radius: 8px; border: 1px solid #d0d0d0; border-left: 4px solid #1f77b4; font-family: Arial, sans-serif; white-space: pre-wrap; word-wrap: break-word; font-size: 13px; line-height: 1.4; max-height: 900px; overflow-y: auto; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                {formatted_laudo}
                </div>
                """, unsafe_allow_html=True)
            else:
                st.error("Laudo.txt não encontrado")

# COLUNA 3: Registro de Defeitos
with col3:
    st.subheader("Registro de Defeitos")
    
    # Botões lado a lado
    btn_col1, btn_col2 = st.columns(2)
    
    with btn_col1:
        if st.button("Inserir Defeito", width='stretch'):
            st.session_state.mostrar_defeito = True
    
    with btn_col2:
        if st.button("Análise do histórico", width='stretch'):
            st.session_state.mostrar_comparacao = True
    
    # Se o botão foi clicado, mostrar análise do histórico
    if st.session_state.get("mostrar_comparacao", False):
        st.write("---")
        st.subheader("Análise do histórico")
        
        diretorio_atual = os.path.dirname(os.path.abspath(__file__))
        caminho_comparacao = os.path.join(diretorio_atual, "comparacao_anterior.txt")
        
        if os.path.exists(caminho_comparacao):
            with open(caminho_comparacao, 'r', encoding='utf-8') as f:
                conteudo_comparacao = f.read()
            # Formatar com primeira linha em negrito e espaçamento entre parágrafos
            lines_comparacao = conteudo_comparacao.split('\n')
            if lines_comparacao:
                first_line = f"<b>{lines_comparacao[0]}</b>"
                rest_content = "\n".join(lines_comparacao[1:]).strip()
                formatted_comparacao = first_line + (f"<br><br>{format_spacing(rest_content)}" if rest_content else "")
            else:
                formatted_comparacao = conteudo_comparacao
            st.markdown(f"""
            <div style="color: #000000; background-color: #f5f5f5; padding: 20px; border-radius: 8px; border: 1px solid #d0d0d0; border-left: 4px solid #2ca02c; font-family: Arial, sans-serif; white-space: pre-wrap; word-wrap: break-word; font-size: 13px; line-height: 1.4; max-height: 800px; overflow-y: auto; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
            {formatted_comparacao}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.warning("Arquivo comparacao_anterior.txt não encontrado")
    
    # Se o botão foi clicado, mostrar a caixa de combinação de defeitos
    if st.session_state.get("mostrar_defeito", False):
        tipos_defeito = [
            "1: Trinca",
            "2: Perda de espessura local",
            "3: Deformação"
        ]
        
        defeito_selecionado = st.selectbox(
            "Tipo de defeito:",
            tipos_defeito
        )
        
        st.success(f"✓ {defeito_selecionado}")
        
        # Se o defeito selecionado é "Trinca", mostrar campo de upload de PDF
        if defeito_selecionado == "1: Trinca":
            st.write("---")
            st.write("**Relatório de UT**")
            
            arquivo_pdf = st.file_uploader(
                "Selecione arquivo PDF",
                type=["pdf"],
                accept_multiple_files=False,
                key="pdf_uploader"
            )
            
            if arquivo_pdf is not None:
                st.success(f"✓ {arquivo_pdf.name}")
                st.caption(f"{arquivo_pdf.size / 1024:.2f} KB")
                
                # Exibir relatório automaticamente após carregamento do PDF
                st.write("")
                
                # Ler conteúdo do arquivo de análise
                diretorio_atual = os.path.dirname(os.path.abspath(__file__))
                caminho_relatorio = os.path.join(diretorio_atual, "Análise do relatório de inspeção.txt")
                
                if os.path.exists(caminho_relatorio):
                    with open(caminho_relatorio, 'r', encoding='utf-8') as f:
                        conteudo_relatorio = f.read()
                    # Formatar com primeira linha em negrito e espaçamento entre parágrafos
                    lines_relatorio = conteudo_relatorio.split('\n')
                    if lines_relatorio:
                        first_line = f"<b>{lines_relatorio[0]}</b>"
                        rest_content = "\n".join(lines_relatorio[1:]).strip()
                        formatted_relatorio = first_line + (f"<br><br>{format_spacing(rest_content)}" if rest_content else "")
                    else:
                        formatted_relatorio = conteudo_relatorio
                    st.markdown(f"""
                    <div style="color: #000000; background-color: #f5f5f5; padding: 20px; border-radius: 8px; border: 1px solid #d0d0d0; border-left: 4px solid #ff7f0e; font-family: Arial, sans-serif; white-space: pre-wrap; word-wrap: break-word; font-size: 13px; line-height: 1.4; max-height: 800px; overflow-y: auto; box-shadow: 0 2px 4px rgba(0,0,0,0.1);">
                    {formatted_relatorio}
                    </div>
                    """, unsafe_allow_html=True)
                else:
                    st.error("Arquivo de análise não encontrado")
