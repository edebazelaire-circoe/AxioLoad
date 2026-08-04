from __future__ import annotations

from typing import Annotated, Any

from fastapi import FastAPI, File, Form, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response

from . import admin_base
from .admin_base import WebContext
from .document_control import DOCUMENT_TYPES, LOCKED_SYSTEM_PROMPT, SYSTEM_PROMPT_VERSION, DocumentControlRepository, call_openai, export_pdf, export_xlsx, prepare_document

_DOCUMENT_PERMISSIONS = (
    {"key":"document_control.view","module":"document_control","label":"Accéder au contrôle documentaire"},
    {"key":"document_control.run","module":"document_control","label":"Lancer un contrôle documentaire"},
    {"key":"document_control.history","module":"document_control","label":"Consulter ses contrôles documentaires"},
    {"key":"document_control.export","module":"document_control","label":"Exporter les rapports documentaires"},
)
_original_fastapi_init = FastAPI.__init__


def install_document_control_permissions() -> None:
    existing={entry["key"] for entry in admin_base.PERMISSION_CATALOG}
    additions=tuple(entry for entry in _DOCUMENT_PERMISSIONS if entry["key"] not in existing)
    if not additions: return
    admin_base.PERMISSION_CATALOG=admin_base.PERMISSION_CATALOG+additions
    admin_base.PERMISSION_KEYS.update(entry["key"] for entry in additions)
    admin_base.DEFAULT_NEW_COMPANY_PERMISSIONS.update({entry["key"]:True for entry in additions})


def _repo(request: Request) -> DocumentControlRepository:
    return DocumentControlRepository(request.app.state.registry)


def _context(request: Request) -> WebContext:
    return request.app.state.admin.resolve_web_context(request.cookies.get("axioload_assistance"),request.cookies.get("axioload_session"))


def _primary(request: Request, context: WebContext) -> bool:
    if context.actor_id=="local-user": return True
    if context.actor_type!="user": return False
    try: return request.app.state.admin.get_user(context.actor_id)["role"]=="primary"
    except KeyError: return False


def _require(request: Request, permission: str, *, write: bool=False) -> WebContext:
    context=_context(request)
    try: request.app.state.admin.require_permission(context,permission,write=write)
    except PermissionError as exc: raise HTTPException(403,str(exc)) from exc
    return context


def _super_admin(request: Request, token: str|None, authorization: str|None) -> str:
    try: return request.app.state.admin.super_admin_actor(token or authorization)
    except PermissionError as exc: raise HTTPException(401,str(exc)) from exc


def _validate_types(left_type: str,right_type: str) -> None:
    allowed={key for key,_ in DOCUMENT_TYPES}
    if left_type not in allowed or right_type not in allowed: raise HTTPException(422,"Type de document inconnu")


def register_document_control_routes(app: FastAPI) -> None:
    if getattr(app.state,"_document_control_registered",False): return
    app.state._document_control_registered=True

    @app.get("/api/document-control/bootstrap")
    def document_bootstrap(request: Request) -> dict[str,Any]:
        context=_require(request,"document_control.view"); config=_repo(request).get_ai_config(context.tenant_id)
        return {"document_types":[{"key":k,"label":v} for k,v in DOCUMENT_TYPES],"limits":{"max_file_mb":10,"max_pdf_pages":20,"formats":["PDF","JPG","JPEG","PNG"]},"security":"Vos documents sont utilisés uniquement pendant l'analyse et ne sont jamais conservés par AxioLoad.","provider_configured":config["configured"],"provider":config["provider"],"model":config["model"],"is_primary_admin":_primary(request,context),"system_prompt_version":SYSTEM_PROMPT_VERSION}

    @app.post("/api/document-control/analyze")
    async def document_analyze(request: Request,left_file:Annotated[UploadFile,File()],right_file:Annotated[UploadFile,File()],left_type:Annotated[str,Form()],right_type:Annotated[str,Form()],title:Annotated[str,Form()]="",user_instruction:Annotated[str,Form()]="") -> dict[str,Any]:
        context=_require(request,"document_control.run",write=True); _validate_types(left_type,right_type); repo=_repo(request)
        config=repo.get_ai_config(context.tenant_id,include_secret=True)
        if not config.get("configured"): raise HTTPException(422,"Le responsable principal doit configurer la connexion IA de cette entreprise dans Paramètres")
        prompt=repo.get_prompt(context.tenant_id,left_type,right_type); left_bytes=await left_file.read(); right_bytes=await right_file.read()
        try:
            left=prepare_document(left_file.filename or "document-1",left_file.content_type,left_bytes); right=prepare_document(right_file.filename or "document-2",right_file.content_type,right_bytes)
            result=call_openai(config,left,right,left_type,right_type,prompt.get("admin_instructions",""),user_instruction)
            control=repo.create_control(context.tenant_id,actor_id=context.actor_id,actor_label=context.actor_label,title=title,left_type=left_type,right_type=right_type,user_instruction=user_instruction,result=result,config=config,prompt=prompt)
            control["prompt_warning"]=None if prompt["configured"] else "Aucun complément métier spécifique n'est configuré. L'analyse a utilisé le socle standard AxioLoad."
            return control
        except (ValueError,RuntimeError) as exc: raise HTTPException(422,str(exc)) from exc
        finally:
            left_bytes=b""; right_bytes=b""

    @app.get("/api/document-control/history")
    def document_history(request: Request) -> list[dict[str,Any]]:
        context=_require(request,"document_control.history"); return _repo(request).list_controls(context.tenant_id,context.actor_id,_primary(request,context))

    @app.get("/api/document-control/history/{control_id}")
    def document_history_detail(request: Request,control_id: str) -> dict[str,Any]:
        context=_require(request,"document_control.history")
        try: return _repo(request).get_control(context.tenant_id,control_id,context.actor_id,_primary(request,context))
        except KeyError as exc: raise HTTPException(404,"Contrôle inconnu") from exc
        except PermissionError as exc: raise HTTPException(403,str(exc)) from exc

    @app.put("/api/document-control/history/{control_id}")
    async def document_history_update(request: Request,control_id: str) -> dict[str,Any]:
        context=_require(request,"document_control.run",write=True); payload=await request.json()
        try: return _repo(request).update_control(context.tenant_id,control_id,context.actor_id,_primary(request,context),payload)
        except KeyError as exc: raise HTTPException(404,"Contrôle inconnu") from exc
        except PermissionError as exc: raise HTTPException(403,str(exc)) from exc
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc

    @app.get("/api/document-control/history/{control_id}/export.pdf")
    def document_export_pdf(request: Request,control_id: str) -> Response:
        context=_require(request,"document_control.export")
        try: control=_repo(request).get_control(context.tenant_id,control_id,context.actor_id,_primary(request,context))
        except KeyError as exc: raise HTTPException(404,"Contrôle inconnu") from exc
        return Response(export_pdf(control),media_type="application/pdf",headers={"Content-Disposition":f'attachment; filename="{control["reference"]}.pdf"',"Cache-Control":"no-store"})

    @app.get("/api/document-control/history/{control_id}/export.xlsx")
    def document_export_xlsx(request: Request,control_id: str) -> Response:
        context=_require(request,"document_control.export")
        try: control=_repo(request).get_control(context.tenant_id,control_id,context.actor_id,_primary(request,context))
        except KeyError as exc: raise HTTPException(404,"Contrôle inconnu") from exc
        return Response(export_xlsx(control),media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",headers={"Content-Disposition":f'attachment; filename="{control["reference"]}.xlsx"',"Cache-Control":"no-store"})

    @app.get("/api/document-control/prompts/{left_type}/{right_type}")
    def document_prompt_get(request: Request,left_type: str,right_type: str) -> dict[str,Any]:
        context=_require(request,"document_control.view"); _validate_types(left_type,right_type)
        if not _primary(request,context): raise HTTPException(403,"Seul l'administrateur principal peut consulter les compléments métier")
        prompt=_repo(request).get_prompt(context.tenant_id,left_type,right_type); prompt["locked_prompt_preview"]=LOCKED_SYSTEM_PROMPT; return prompt

    @app.put("/api/document-control/prompts/{left_type}/{right_type}")
    async def document_prompt_save(request: Request,left_type: str,right_type: str) -> dict[str,Any]:
        context=_require(request,"document_control.run",write=True); _validate_types(left_type,right_type)
        if not _primary(request,context): raise HTTPException(403,"Seul l'administrateur principal peut modifier les compléments métier")
        payload=await request.json()
        try: return _repo(request).save_prompt(context.tenant_id,left_type,right_type,str(payload.get("admin_instructions") or ""),context.actor_label)
        except ValueError as exc: raise HTTPException(422,str(exc)) from exc

    @app.get("/api/admin/companies/{tenant_id}/document-ai")
    def admin_document_ai_get(request: Request,tenant_id: str,x_axioload_super_admin:Annotated[str|None,Header()]=None,authorization:Annotated[str|None,Header()]=None) -> dict[str,Any]:
        _super_admin(request,x_axioload_super_admin,authorization)
        try: request.app.state.admin.get_company(tenant_id)
        except KeyError as exc: raise HTTPException(404,"Entreprise inconnue") from exc
        return _repo(request).get_ai_config(tenant_id)

    @app.put("/api/admin/companies/{tenant_id}/document-ai")
    async def admin_document_ai_save(request: Request,tenant_id: str,x_axioload_super_admin:Annotated[str|None,Header()]=None,authorization:Annotated[str|None,Header()]=None) -> dict[str,Any]:
        actor=_super_admin(request,x_axioload_super_admin,authorization); payload=await request.json()
        try:
            request.app.state.admin.get_company(tenant_id); result=_repo(request).save_ai_config(tenant_id,payload,actor)
            request.app.state.admin.audit(tenant_id,actor,"document_ai.config.updated",tenant_id,{},result); return result
        except KeyError as exc: raise HTTPException(404,"Entreprise inconnue") from exc
        except (ValueError,RuntimeError) as exc: raise HTTPException(422,str(exc)) from exc


def install_document_control_routes() -> None:
    if getattr(FastAPI.__init__,"_axioload_document_control",False): return
    def init(self: FastAPI,*args:Any,**kwargs:Any) -> None:
        _original_fastapi_init(self,*args,**kwargs); register_document_control_routes(self)
    init._axioload_document_control=True  # type: ignore[attr-defined]
    FastAPI.__init__=init  # type: ignore[method-assign]
