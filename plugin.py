import gradio as gr
import os
import json
import subprocess
import platform
from datetime import datetime
from shared.utils.plugins import WAN2GPPlugin


class ModelManagerPlugin(WAN2GPPlugin):
    """Model Manager Plugin V2 for Wan2GP."""
    
    def __init__(self):
        super().__init__()
        self.name = "Model Manager"
        self.version = "2.0.0"
        self.description = "Manage installed models. View sizes, search, filter by type, and delete unused models."
        
        self.plugin_dir = os.path.dirname(os.path.abspath(__file__))
        self.default_model_dirs = ["ckpts"]
        self.model_extensions = [".safetensors", ".sft", ".pth", ".pt", ".ckpt"]
        self.usage_file = os.path.join(self.plugin_dir, "model_usage.json")
        
        self.models_cache = []
    def setup_ui(self):
        self.request_global("server_config")
        self.add_tab(
            tab_id="model_manager_tab",
            label="Model Manager",
            component_constructor=self.create_manager_ui,
            position=4
        )

    def get_model_dirs(self):
        try:
            if hasattr(self, 'server_config') and self.server_config:
                paths = self.server_config.get("checkpoints_paths", self.default_model_dirs)
                return [p for p in paths if os.path.isdir(p)]
        except:
            pass
        return [d for d in self.default_model_dirs if os.path.isdir(d)]

    def format_size(self, size_bytes):
        if size_bytes < 1024:
            return f"{size_bytes} B"
        elif size_bytes < 1024 ** 2:
            return f"{size_bytes / 1024:.1f} KB"
        elif size_bytes < 1024 ** 3:
            return f"{size_bytes / (1024 ** 2):.1f} MB"
        else:
            return f"{size_bytes / (1024 ** 3):.2f} GB"

    def detect_model_type(self, filename, path, size_bytes):
        name_lower = filename.lower()
        path_lower = path.lower()
        size_gb = size_bytes / (1024 ** 3)
        
        if "lora" in path_lower or "loras" in path_lower or "_lora" in name_lower:
            return ("LoRA", "#22c55e", "🎨")
        if "vae" in name_lower:
            return ("VAE", "#a855f7", "🎭")
        if any(x in name_lower for x in ["clip", "text_encoder", "t5", "umt5", "xlm", "roberta"]):
            return ("Text Encoder", "#f97316", "📝")
        if any(x in name_lower for x in ["llama", "qwen", "gemma", "caption", "joycaption"]):
            return ("LLM", "#06b6d4", "🧠")
        if any(x in name_lower for x in ["upscal", "esrgan", "swinir", "flashvsr"]):
            return ("Upscaler", "#ec4899", "⬆️")
        if any(x in name_lower for x in ["depth", "midas"]):
            return ("Depth", "#8b5cf6", "🌊")
        if any(x in name_lower for x in ["audio", "mmaudio", "roformer"]):
            return ("Audio", "#f59e0b", "🔊")
        if any(x in name_lower for x in ["sam", "segment"]):
            return ("Segmentation", "#84cc16", "✂️")
        if any(x in name_lower for x in ["wan2", "ltx", "flux", "hunyuan"]):
            return ("Checkpoint", "#3b82f6", "🔷") if size_gb > 5 else ("Model", "#60a5fa", "📦")
        if size_gb > 10:
            return ("Checkpoint", "#3b82f6", "🔷")
        elif size_gb < 0.5:
            return ("LoRA", "#22c55e", "🎨")
        return ("Model", "#60a5fa", "📦")

    def open_folder(self, model_path):
        if not model_path or not os.path.exists(model_path):
            return "❌ File not found"
        folder = os.path.dirname(model_path)
        try:
            if platform.system() == "Windows":
                subprocess.Popen(f'explorer /select,"{model_path}"')
            else:
                subprocess.Popen(["xdg-open", folder])
            return f"✅ Opened: {folder}"
        except Exception as e:
            return f"❌ Error: {e}"

    def scan_models(self, scan_dirs=None):
        if scan_dirs is None:
            scan_dirs = self.get_model_dirs()
        
        models = []
        seen_paths = set()
        
        for base_dir in scan_dirs:
            if not os.path.isdir(base_dir):
                continue
            abs_base_dir = os.path.abspath(base_dir)
            for root, dirs, files in os.walk(abs_base_dir):
                dirs[:] = [d for d in dirs if not d.startswith('.')]
                for filename in files:
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in self.model_extensions:
                        full_path = os.path.abspath(os.path.join(root, filename))
                        if full_path in seen_paths:
                            continue
                        seen_paths.add(full_path)
                        try:
                            stat = os.stat(full_path)
                            rel_path = os.path.relpath(full_path, abs_base_dir)
                            model_type, type_color, type_icon = self.detect_model_type(filename, full_path, stat.st_size)
                            models.append({
                                "name": filename,
                                "path": full_path,
                                "rel_path": rel_path,
                                "base_dir": base_dir,
                                "size": stat.st_size,
                                "size_str": self.format_size(stat.st_size),
                                "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                                "model_type": model_type,
                                "type_color": type_color,
                                "type_icon": type_icon
                            })
                        except OSError:
                            continue
        
        models.sort(key=lambda x: x["size"], reverse=True)
        self.models_cache = models
        return models

    def filter_models(self, models, search_query="", type_filter="All"):
        filtered = models
        if search_query:
            query = search_query.lower().strip()
            filtered = [m for m in filtered if query in m["name"].lower()]
        if type_filter and type_filter != "All":
            filtered = [m for m in filtered if m["model_type"] == type_filter]
        return filtered

    def get_unique_types(self, models):
        types = set(m["model_type"] for m in models)
        return ["All"] + sorted(list(types))

    def render_model_list(self, models, sort_by="size", search_query="", type_filter="All"):
        """Render list of models as CheckboxGroup choices (Grid mode)."""
        filtered = self.filter_models(models, search_query, type_filter)
        
        if sort_by == "name":
            filtered = sorted(filtered, key=lambda x: x["name"].lower())
        elif sort_by == "date":
            filtered = sorted(filtered, key=lambda x: x["modified"], reverse=True)
        else:
            filtered = sorted(filtered, key=lambda x: x["size"], reverse=True)
        
        choices = []
        for m in filtered:
            label = f"{m['type_icon']} {m['name']} | {m['size_str']}"
            choices.append((label, m["path"]))
        
        return choices, filtered

    def render_detailed_list(self, models, selected_paths, sort_by="size", search_query="", type_filter="All"):
        """Render detailed HTML list (List mode)."""
        filtered = self.filter_models(models, search_query, type_filter)
        
        if sort_by == "name":
            filtered = sorted(filtered, key=lambda x: x["name"].lower())
        elif sort_by == "date":
            filtered = sorted(filtered, key=lambda x: x["modified"], reverse=True)
        else:
            filtered = sorted(filtered, key=lambda x: x["size"], reverse=True)
        
        if not filtered:
            return "<div style='color:#888;padding:40px;text-align:center;'>📭 No models found</div>", filtered
        
        html = """<style>
            .mm-list{max-height:450px;overflow-y:auto;border:1px solid #374151;border-radius:10px;background:#1f2937;}
            .mm-item{display:flex;align-items:center;padding:12px 16px;border-bottom:1px solid #374151;gap:12px;}
            .mm-item:last-child{border-bottom:none;}
            .mm-item:hover{background:#2d3748;}
            .mm-item.sel{background:rgba(59,130,246,0.15);}
            .mm-cb{width:18px;height:18px;accent-color:#3b82f6;}
            .mm-info{flex:1;min-width:0;}
            .mm-name{font-weight:600;color:#fff;font-size:0.9em;}
            .mm-path{font-size:0.7em;color:#9ca3af;margin-top:2px;}
            .mm-type{padding:3px 8px;border-radius:4px;font-size:0.7em;font-weight:600;}
            .mm-usage{font-size:0.75em;color:#9ca3af;min-width:70px;}
            .mm-usage.never{color:#ef4444;}
            .mm-date{font-size:0.7em;color:#6b7280;min-width:90px;}
            .mm-size{font-weight:700;color:#60a5fa;font-size:0.9em;min-width:70px;text-align:right;}
        </style><div class="mm-list">"""
        
        for m in filtered:
            is_sel = m["path"] in selected_paths
            sel_class = "sel" if is_sel else ""
            checked = "checked" if is_sel else ""
            path_esc = m["path"].replace("\\", "\\\\").replace("'", "\\'")
            
            html += f'''<div class="mm-item {sel_class}">
                <input type="checkbox" class="mm-cb" {checked} onchange="mmToggle(this, '{path_esc}')">
                <div class="mm-info"><div class="mm-name">{m["name"]}</div><div class="mm-path">📁 {m["rel_path"]}</div></div>
                <span class="mm-type" style="background:{m['type_color']};color:white;">{m['type_icon']} {m['model_type']}</span>
                <span class="mm-date">📅 {m["modified"]}</span>
                <span class="mm-size">{m["size_str"]}</span>
            </div>'''
        
        html += "</div>"
        return html, filtered

    def get_stats_html(self, models, selected_paths):
        total_size = sum(m["size"] for m in models)
        selected_size = sum(m["size"] for m in models if m["path"] in selected_paths)
        
        return f"""
        <div style="display:flex; gap:30px; padding:12px 20px; background:linear-gradient(135deg,#1e3a5f,#2d4a6f); border-radius:10px; color:white; margin-bottom:10px;">
            <div style="text-align:center;"><div style="font-size:1.3em;font-weight:700;">📦 {len(models)}</div><div style="font-size:0.75em;opacity:0.8;">Models</div></div>
            <div style="text-align:center;"><div style="font-size:1.3em;font-weight:700;">💾 {self.format_size(total_size)}</div><div style="font-size:0.75em;opacity:0.8;">Total</div></div>
            <div style="text-align:center;"><div style="font-size:1.3em;font-weight:700;">✅ {len(selected_paths)}</div><div style="font-size:0.75em;opacity:0.8;">Selected</div></div>
            <div style="text-align:center;"><div style="font-size:1.3em;font-weight:700;">🗑️ {self.format_size(selected_size)}</div><div style="font-size:0.75em;opacity:0.8;">To Delete</div></div>
        </div>
        """

    def delete_models(self, selected_paths):
        if not selected_paths:
            return "❌ No models selected for deletion"
        
        deleted = []
        errors = []
        freed = 0
        
        for path in selected_paths:
            try:
                if os.path.exists(path):
                    size = os.path.getsize(path)
                    os.remove(path)
                    deleted.append(os.path.basename(path))
                    freed += size
            except Exception as e:
                errors.append(f"{os.path.basename(path)}: {e}")
        
        msg = ""
        if deleted:
            msg = f"✅ Deleted {len(deleted)} files ({self.format_size(freed)} freed)\n"
            msg += "• " + "\n• ".join(deleted[:5])
            if len(deleted) > 5:
                msg += f"\n... and {len(deleted)-5} more"
        if errors:
            msg += f"\n\n⚠️ Errors:\n• " + "\n• ".join(errors[:3])
        
        return msg if msg else "❌ Nothing deleted"

    def create_manager_ui(self):
        """Create the Model Manager UI using native Gradio components."""
        
        with gr.Row():
            gr.Markdown("### 📦 Model Manager")
        
        with gr.Row():
            search_box = gr.Textbox(label="🔍 Search", placeholder="Filter by name...", scale=2)
            type_filter = gr.Dropdown(choices=["All"], value="All", label="🏷️ Type", scale=1)
            sort_dropdown = gr.Dropdown(
                choices=[("Size ↓", "size"), ("Name", "name"), ("Date", "date")],
                value="size", label="Sort", scale=1
            )
            view_mode = gr.Radio(choices=["📊 Grid", "📋 List"], value="📊 Grid", label="View", scale=1)
            refresh_btn = gr.Button("🔄", scale=0, min_width=50)
        
        stats_html = gr.HTML()
        
        # Grid view (CheckboxGroup)
        model_selector = gr.CheckboxGroup(
            choices=[],
            label="Models",
            interactive=True,
            visible=True
        )
        
        # List view (HTML + hidden selection state)
        list_html = gr.HTML(visible=False)
        list_selection = gr.Textbox(visible=False, value="[]", elem_id="mm_list_sel")
        
        with gr.Row():
            open_folder_btn = gr.Button("📂 Open Folder", scale=1)
            delete_btn = gr.Button("🗑️ Delete Selected", variant="stop", scale=1)
        
        status_box = gr.Textbox(label="Status", interactive=False, lines=3)
        
        with gr.Accordion("⚠️ Warning", open=False):
            gr.Markdown("**Deletion is permanent!** Files do NOT go to recycle bin.")
        
        # Add JS for list mode selection
        self.add_custom_js("""
            window.mmToggle = function(cb, path) {
                const sel = document.getElementById('mm_list_sel');
                if (!sel) return;
                const ta = sel.querySelector('textarea');
                if (!ta) return;
                let arr = [];
                try { arr = JSON.parse(ta.value || '[]'); } catch(e) {}
                if (cb.checked) {
                    if (!arr.includes(path)) arr.push(path);
                    cb.closest('.mm-item').classList.add('sel');
                } else {
                    arr = arr.filter(x => x !== path);
                    cb.closest('.mm-item').classList.remove('sel');
                }
                ta.value = JSON.stringify(arr);
                ta.dispatchEvent(new Event('input', {bubbles:true}));
            }
        """)
        
        # Functions
        def do_refresh(sort_by, search_q, type_f, view):
            models = self.scan_models()
            choices, filtered = self.render_model_list(models, sort_by, search_q, type_f)
            types = self.get_unique_types(models)
            stats = self.get_stats_html(filtered, [])
            
            is_list = "List" in view
            if is_list:
                list_h, _ = self.render_detailed_list(models, set(), sort_by, search_q, type_f)
                return (gr.update(choices=choices, value=[], visible=not is_list), 
                        stats, gr.update(choices=types), "",
                        gr.update(value=list_h, visible=is_list), "[]")
            else:
                return (gr.update(choices=choices, value=[], visible=True), 
                        stats, gr.update(choices=types), "",
                        gr.update(visible=False), "[]")
        
        def on_view_change(view, sort_by, search_q, type_f, grid_sel, list_sel_json):
            models = self.models_cache or self.scan_models()
            is_list = "List" in view
            
            if is_list:
                # Switch to list - transfer selection
                sel = set(grid_sel or [])
                list_h, filtered = self.render_detailed_list(models, sel, sort_by, search_q, type_f)
                stats = self.get_stats_html(filtered, sel)
                return (gr.update(visible=False), 
                        gr.update(value=list_h, visible=True), 
                        json.dumps(list(sel)),
                        stats)
            else:
                # Switch to grid - transfer selection
                sel = []
                try:
                    sel = json.loads(list_sel_json) if list_sel_json else []
                except:
                    pass
                choices, filtered = self.render_model_list(models, sort_by, search_q, type_f)
                valid = [c[1] for c in choices]
                kept = [s for s in sel if s in valid]
                stats = self.get_stats_html(filtered, kept)
                return (gr.update(choices=choices, value=kept, visible=True), 
                        gr.update(visible=False), 
                        "[]",
                        stats)
        
        def on_filter_change(sort_by, search_q, type_f, grid_sel, view, list_sel_json):
            models = self.models_cache or self.scan_models()
            is_list = "List" in view
            
            if is_list:
                sel = set()
                try:
                    sel = set(json.loads(list_sel_json)) if list_sel_json else set()
                except:
                    pass
                list_h, filtered = self.render_detailed_list(models, sel, sort_by, search_q, type_f)
                stats = self.get_stats_html(filtered, sel)
                return gr.update(), gr.update(value=list_h), stats
            else:
                choices, filtered = self.render_model_list(models, sort_by, search_q, type_f)
                valid = [c[1] for c in choices]
                kept = [s for s in (grid_sel or []) if s in valid]
                stats = self.get_stats_html(filtered, kept)
                return gr.update(choices=choices, value=kept), gr.update(), stats
        
        def on_grid_selection(selected, sort_by, search_q, type_f):
            models = self.models_cache or self.scan_models()
            _, filtered = self.render_model_list(models, sort_by, search_q, type_f)
            stats = self.get_stats_html(filtered, selected or [])
            return stats
        
        def on_list_selection(list_sel_json, sort_by, search_q, type_f):
            sel = []
            try:
                sel = json.loads(list_sel_json) if list_sel_json else []
            except:
                pass
            models = self.models_cache or self.scan_models()
            _, filtered = self.render_detailed_list(models, set(sel), sort_by, search_q, type_f)
            stats = self.get_stats_html(filtered, sel)
            list_h, _ = self.render_detailed_list(models, set(sel), sort_by, search_q, type_f)
            return stats, list_h
        
        def do_delete(grid_sel, list_sel_json, view, sort_by, search_q, type_f):
            is_list = "List" in view
            if is_list:
                try:
                    sel = json.loads(list_sel_json) if list_sel_json else []
                except:
                    sel = []
            else:
                sel = grid_sel or []
            
            msg = self.delete_models(sel)
            models = self.scan_models()
            
            if is_list:
                list_h, filtered = self.render_detailed_list(models, set(), sort_by, search_q, type_f)
                stats = self.get_stats_html(filtered, [])
                return msg, gr.update(), gr.update(value=list_h), "[]", stats
            else:
                choices, filtered = self.render_model_list(models, sort_by, search_q, type_f)
                stats = self.get_stats_html(filtered, [])
                return msg, gr.update(choices=choices, value=[]), gr.update(), "[]", stats
        
        def do_open_folder(grid_sel, list_sel_json, view):
            is_list = "List" in view
            if is_list:
                try:
                    sel = json.loads(list_sel_json) if list_sel_json else []
                except:
                    sel = []
            else:
                sel = grid_sel or []
            
            if not sel:
                return "❌ Select a model first"
            return self.open_folder(sel[0])
        
        # Wire events
        refresh_btn.click(
            fn=do_refresh,
            inputs=[sort_dropdown, search_box, type_filter, view_mode],
            outputs=[model_selector, stats_html, type_filter, status_box, list_html, list_selection]
        )
        
        view_mode.change(
            fn=on_view_change,
            inputs=[view_mode, sort_dropdown, search_box, type_filter, model_selector, list_selection],
            outputs=[model_selector, list_html, list_selection, stats_html]
        )
        
        search_box.change(
            fn=on_filter_change,
            inputs=[sort_dropdown, search_box, type_filter, model_selector, view_mode, list_selection],
            outputs=[model_selector, list_html, stats_html]
        )
        
        type_filter.change(
            fn=on_filter_change,
            inputs=[sort_dropdown, search_box, type_filter, model_selector, view_mode, list_selection],
            outputs=[model_selector, list_html, stats_html]
        )
        
        sort_dropdown.change(
            fn=on_filter_change,
            inputs=[sort_dropdown, search_box, type_filter, model_selector, view_mode, list_selection],
            outputs=[model_selector, list_html, stats_html]
        )
        
        model_selector.change(
            fn=on_grid_selection,
            inputs=[model_selector, sort_dropdown, search_box, type_filter],
            outputs=[stats_html]
        )
        
        list_selection.change(
            fn=on_list_selection,
            inputs=[list_selection, sort_dropdown, search_box, type_filter],
            outputs=[stats_html, list_html]
        )
        
        delete_btn.click(
            fn=do_delete,
            inputs=[model_selector, list_selection, view_mode, sort_dropdown, search_box, type_filter],
            outputs=[status_box, model_selector, list_html, list_selection, stats_html]
        )
        
        open_folder_btn.click(
            fn=do_open_folder,
            inputs=[model_selector, list_selection, view_mode],
            outputs=[status_box]
        )
        
        # Store for tab events
        self.model_selector = model_selector
        self.stats_html = stats_html
        self.status_box = status_box
        self.sort_dropdown = sort_dropdown
        self.search_box = search_box
        self.type_filter = type_filter
        self.view_mode = view_mode
        self.list_html = list_html
        self.list_selection = list_selection
        self.on_tab_outputs = [model_selector, stats_html, type_filter, status_box, list_html, list_selection]

    def on_tab_select(self, state):
        """Auto refresh on tab select."""
        models = self.scan_models()
        choices, filtered = self.render_model_list(models, "size", "", "All")
        types = self.get_unique_types(models)
        stats = self.get_stats_html(filtered, [])
        return gr.update(choices=choices, value=[]), stats, gr.update(choices=types), "", gr.update(visible=False), "[]"

