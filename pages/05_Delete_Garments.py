import base64
import io
import os

import gridfs
from bson import ObjectId
try:
    from dotenv import load_dotenv
except Exception:
    load_dotenv = None
from PIL import Image
from pymongo import MongoClient
from pymongo.errors import ServerSelectionTimeoutError
import streamlit as st

from brand_theme import inject_glass_css, render_footer, render_top_nav

BRAND = "VibeCheck"

st.set_page_config(page_title=f"{BRAND} | Delete Garments", layout="wide")
inject_glass_css(hide_sidebar=True)
render_top_nav(active="app")


def get_config_value(key: str, default: str = "") -> str:
    try:
        val = st.secrets.get(key, None)
    except Exception:
        val = None

    if isinstance(val, str):
        val = val.strip()
    if val:
        return val

    if load_dotenv is not None:
        try:
            load_dotenv(override=True)
        except Exception:
            pass

    env_val = os.environ.get(key, default)
    if isinstance(env_val, str):
        env_val = env_val.strip()
    return env_val


@st.cache_resource
def mongo():
    uri = get_config_value("MONGO_URI", "")
    db_name = get_config_value("MONGO_DB", "Wardrobe_db") or "Wardrobe_db"
    if not uri:
        raise RuntimeError("Missing MONGO_URI in Streamlit secrets or .env")

    print("[VibeCheck] Connecting Mongo client for Delete Garments page (cached)")
    client = MongoClient(
        uri,
        serverSelectionTimeoutMS=8000,
        connectTimeoutMS=8000,
        socketTimeoutMS=8000,
    )
    db = client[db_name]
    db.command("ping")
    fs = gridfs.GridFS(db)
    return client, db, fs


@st.cache_data(show_spinner=False, ttl=900, max_entries=64)
def fs_get_bytes(file_id_str: str) -> bytes:
    _client, _db, fs = mongo()
    return fs.get(ObjectId(file_id_str)).read()


def get_image_from_fs(file_id_str: str) -> Image.Image:
    data = fs_get_bytes(file_id_str)
    with Image.open(io.BytesIO(data)) as img:
        return img.convert("RGBA")


def image_to_png_bytes(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_image_card(img: Image.Image, caption: str = ""):
    if img.mode not in ("RGB", "RGBA"):
        img = img.convert("RGBA")
    b64 = base64.b64encode(image_to_png_bytes(img)).decode("ascii")
    st.markdown(
        f"""
<div class="card" style="padding:8px;">
  <div class="media-frame" style="aspect-ratio:4/5;">
    <img src="data:image/png;base64,{b64}" alt="{caption}" />
  </div>
  <p class="muted" style="margin:10px 0 0 0; font-size:13px;">{caption}</p>
</div>
""",
        unsafe_allow_html=True,
    )


@st.cache_data(show_spinner=False, ttl=120, max_entries=12)
def get_related_outfit_counts_for_page(customer_id: str, garment_refs: tuple):
    _client, db, _fs = mongo()
    counts = {}

    shirt_ids = [gid for part, gid in garment_refs if part == "shirt"]
    pants_ids = [gid for part, gid in garment_refs if part == "pants"]
    shoes_ids = [gid for part, gid in garment_refs if part == "shoes"]

    if shirt_ids:
        for row in db["Outfits"].aggregate([
            {"$match": {"customer_id": customer_id, "shirt_id": {"$in": shirt_ids}}},
            {"$group": {"_id": "$shirt_id", "count": {"$sum": 1}}},
        ]):
            counts[("shirt", str(row["_id"]))] = int(row["count"])

    if pants_ids:
        for row in db["Outfits"].aggregate([
            {"$match": {"customer_id": customer_id, "pants_id": {"$in": pants_ids}}},
            {"$group": {"_id": "$pants_id", "count": {"$sum": 1}}},
        ]):
            counts[("pants", str(row["_id"]))] = int(row["count"])

    if shoes_ids:
        for row in db["Outfits"].aggregate([
            {"$match": {"customer_id": customer_id, "shoes_id": {"$in": shoes_ids}}},
            {"$group": {"_id": "$shoes_id", "count": {"$sum": 1}}},
        ]):
            counts[("shoes", str(row["_id"]))] = int(row["count"])

    return counts


@st.cache_data(show_spinner=False, ttl=120, max_entries=12)
def get_garments_page(customer_id: str, part_filter: str, page_num: int, page_size: int):
    _client, db, _fs = mongo()

    q = {"customer_id": customer_id}
    if part_filter != "all":
        q["part"] = part_filter

    total = int(db["Wardrobe"].count_documents(q))
    skip = max(0, (int(page_num) - 1) * int(page_size))

    projection = {
        "_id": 1,
        "part": 1,
        "tags": 1,
        "created_at": 1,
        "image_fs_id": 1,
    }
    docs = list(
        db["Wardrobe"]
        .find(q, projection)
        .sort("created_at", -1)
        .skip(skip)
        .limit(int(page_size))
    )
    return total, docs


def delete_garment_and_related_outfits(db, fs, customer_id: str, garment_doc: dict):
    part = garment_doc.get("part")
    gid = str(garment_doc.get("_id"))
    field = {"shirt": "shirt_id", "pants": "pants_id", "shoes": "shoes_id"}.get(part)

    deleted_outfits = 0
    if field:
        deleted_outfits = db["Outfits"].delete_many({"customer_id": customer_id, field: gid}).deleted_count

    db["Wardrobe"].delete_one({"_id": garment_doc["_id"], "customer_id": customer_id})

    img_fs_id = garment_doc.get("image_fs_id")
    if img_fs_id:
        try:
            fs.delete(ObjectId(str(img_fs_id)))
        except Exception:
            pass

    st.cache_data.clear()
    return deleted_outfits


st.markdown(
    """
<div class="landing-shell page-shell">
  <div class="glass-panel hero-panel">
    <p class="eyebrow">Account Tools</p>
    <h1 style="margin:10px 0 8px 0; font-size:1.7rem;">Delete Garments</h1>
    <p class="hero-sub">Delete garments safely. Related saved outfits will be removed automatically.</p>
  </div>
</div>
""",
    unsafe_allow_html=True,
)

auth_user = st.session_state.get("auth_user")
if auth_user is None:
    st.warning("Login is required to manage garments.")
    st.page_link("wardrobe_app_auth.py", label="Go to Login")
    st.stop()

customer_id = str(auth_user["_id"])

st.caption("Connecting to DB (cached)")
try:
    _mongo_client, db, fs = mongo()
except Exception as e:
    st.error("MongoDB connection failed.")
    st.caption(f"Error type: {type(e).__name__}")
    if isinstance(e, ServerSelectionTimeoutError):
        st.markdown(
            """
**MongoDB Atlas checklist**
- Confirm Streamlit secrets include `MONGO_URI` and `MONGO_DB`.
- In Atlas `Network Access`, allow Streamlit Cloud egress (or temporarily allow `0.0.0.0/0` for testing).
- Verify the Atlas DB user/password in `MONGO_URI` are correct and URL-encoded.
- Verify the Atlas cluster is running and reachable.
"""
        )
    else:
        st.caption(str(e))
    st.stop()

delete_toast = st.session_state.pop("delete_garment_toast", None)
if delete_toast:
    st.toast(delete_toast, icon="✅")

f1, f2 = st.columns([1, 1])
with f1:
    part_filter = st.selectbox("Garment type", ["all", "shirt", "pants", "shoes"], key="delete_part_filter")
with f2:
    page_size = st.slider("Items shown", 10, 200, 40, 10, key="delete_limit")

total_count, _ = get_garments_page(customer_id, part_filter, 1, page_size)
total_pages = max(1, (total_count + page_size - 1) // page_size)

pcol1, pcol2 = st.columns([1, 3])
with pcol1:
    page_num = int(
        st.number_input(
            "Page",
            min_value=1,
            max_value=total_pages,
            value=1,
            step=1,
            key="delete_page_num",
        )
    )
with pcol2:
    start_idx = (page_num - 1) * page_size + 1 if total_count > 0 else 0
    end_idx = min(total_count, page_num * page_size)
    st.caption(f"Showing {start_idx}-{end_idx} of {total_count} garment(s)")

total_count, garments = get_garments_page(customer_id, part_filter, page_num, page_size)
garment_refs = tuple((str(g.get("part")), str(g.get("_id"))) for g in garments)
ref_counts = get_related_outfit_counts_for_page(customer_id, garment_refs) if garments else {}

if not garments:
    st.markdown('<div class="page-shell card"><p class="muted" style="margin:0;">No garments found for this filter.</p></div>', unsafe_allow_html=True)
else:
    st.caption(f"{len(garments)} garment(s) on this page")

for g in garments:
    c1, c2, c3 = st.columns([1.2, 1.6, 1.2], gap="large")
    with c1:
        try:
            render_image_card(get_image_from_fs(g["image_fs_id"]), caption=g.get("part", "item"))
        except Exception:
            st.markdown('<div class="card"><p class="muted">Image unavailable.</p></div>', unsafe_allow_html=True)

    with c2:
        st.markdown(
            f"""
<div class="card">
  <p class="kicker">Garment</p>
  <p style="font-size:1.05rem; margin:6px 0; font-weight:700;">{g.get('part', 'item').title()}</p>
  <p class="muted" style="margin:0 0 8px 0;">Tags: {g.get('tags', [])}</p>
  <p class="muted" style="margin:0;">Created: {g.get('created_at')}</p>
</div>
""",
            unsafe_allow_html=True,
        )

    with c3:
        ref_count = int(ref_counts.get((str(g.get("part")), str(g["_id"])), 0))
        st.markdown(
            f"""
<div class="card">
  <p class="kicker">Impact</p>
  <p class="muted" style="margin:8px 0 16px 0;">Related outfits: {ref_count}</p>
</div>
""",
            unsafe_allow_html=True,
        )
        confirm_key = f"confirm_delete_{g.get('_id')}"
        st.checkbox("I understand this cannot be undone", key=confirm_key)
        if st.button("Delete Garment", key=f"delete_{g.get('_id')}", use_container_width=True):
            if not st.session_state.get(confirm_key, False):
                st.error("Please confirm deletion first.")
            else:
                deleted_outfits = delete_garment_and_related_outfits(db, fs, customer_id, g)
                st.session_state["delete_garment_toast"] = (
                    f"Deleted successfully. Removed {deleted_outfits} related outfit(s)."
                )
                st.rerun()

    st.divider()

render_footer()
