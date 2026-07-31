--
-- PostgreSQL database dump
--

\restrict TMF6GmOs4Y2fx8x2fDkv1qs7eLjlzFBEIBz6eUA33Su63w3qv3RR89hhNZ2XBtX

-- Dumped from database version 18.1
-- Dumped by pg_dump version 18.1

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET transaction_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: asset_deletion_records; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.asset_deletion_records (
    id integer NOT NULL,
    asset_id integer NOT NULL,
    asset_tag character varying NOT NULL,
    asset_data text,
    deletion_reason text NOT NULL,
    deleted_by integer NOT NULL,
    deleted_at timestamp without time zone
);


ALTER TABLE public.asset_deletion_records OWNER TO postgres;

--
-- Name: asset_deletion_records_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.asset_deletion_records_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.asset_deletion_records_id_seq OWNER TO postgres;

--
-- Name: asset_deletion_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.asset_deletion_records_id_seq OWNED BY public.asset_deletion_records.id;


--
-- Name: asset_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.asset_logs (
    id integer NOT NULL,
    asset_id integer,
    action character varying NOT NULL,
    description text,
    old_value text,
    new_value text,
    operator character varying,
    created_at timestamp without time zone
);


ALTER TABLE public.asset_logs OWNER TO postgres;

--
-- Name: asset_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.asset_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.asset_logs_id_seq OWNER TO postgres;

--
-- Name: asset_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.asset_logs_id_seq OWNED BY public.asset_logs.id;


--
-- Name: asset_part_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.asset_part_logs (
    id integer NOT NULL,
    asset_id integer NOT NULL,
    warehouse_item_id integer,
    warehouse_item_name character varying NOT NULL,
    action character varying NOT NULL,
    quantity integer NOT NULL,
    notes text,
    operator character varying,
    created_at timestamp without time zone
);


ALTER TABLE public.asset_part_logs OWNER TO postgres;

--
-- Name: asset_part_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.asset_part_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.asset_part_logs_id_seq OWNER TO postgres;

--
-- Name: asset_part_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.asset_part_logs_id_seq OWNED BY public.asset_part_logs.id;


--
-- Name: assets; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.assets (
    id integer NOT NULL,
    asset_tag character varying NOT NULL,
    category character varying NOT NULL,
    brand character varying,
    model character varying,
    serial_number character varying,
    status character varying NOT NULL,
    purchase_date timestamp without time zone,
    notes text,
    employee_id character varying,
    employee_name character varying,
    department character varying,
    hostname character varying,
    mac_address character varying,
    ip_address character varying,
    fixed_asset_number character varying,
    system_version character varying,
    antivirus_software character varying,
    issue_date timestamp without time zone,
    lock_number character varying,
    supervisor character varying,
    location character varying,
    po_number character varying,
    condition character varying,
    bios_password boolean,
    tpm_status boolean,
    has_desktop boolean,
    quantity integer,
    additional_info json,
    from_warehouse boolean NOT NULL,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    is_deleted boolean NOT NULL,
    deleted_at timestamp without time zone
);


ALTER TABLE public.assets OWNER TO postgres;

--
-- Name: assets_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.assets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.assets_id_seq OWNER TO postgres;

--
-- Name: assets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.assets_id_seq OWNED BY public.assets.id;


--
-- Name: brands; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.brands (
    id integer NOT NULL,
    name character varying NOT NULL,
    created_at timestamp without time zone
);


ALTER TABLE public.brands OWNER TO postgres;

--
-- Name: brands_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.brands_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.brands_id_seq OWNER TO postgres;

--
-- Name: brands_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.brands_id_seq OWNED BY public.brands.id;


--
-- Name: departments; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.departments (
    id integer NOT NULL,
    name character varying NOT NULL,
    parent_id integer,
    created_at timestamp without time zone
);


ALTER TABLE public.departments OWNER TO postgres;

--
-- Name: departments_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.departments_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.departments_id_seq OWNER TO postgres;

--
-- Name: departments_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.departments_id_seq OWNED BY public.departments.id;


--
-- Name: hostname_history; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.hostname_history (
    id integer NOT NULL,
    asset_id integer NOT NULL,
    old_hostname character varying,
    new_hostname character varying,
    change_reason character varying,
    changed_at timestamp without time zone
);


ALTER TABLE public.hostname_history OWNER TO postgres;

--
-- Name: hostname_history_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.hostname_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.hostname_history_id_seq OWNER TO postgres;

--
-- Name: hostname_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.hostname_history_id_seq OWNED BY public.hostname_history.id;


--
-- Name: office_locations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.office_locations (
    id integer NOT NULL,
    name character varying(100),
    description character varying(255)
);


ALTER TABLE public.office_locations OWNER TO postgres;

--
-- Name: office_locations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.office_locations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.office_locations_id_seq OWNER TO postgres;

--
-- Name: office_locations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.office_locations_id_seq OWNED BY public.office_locations.id;


--
-- Name: operation_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.operation_logs (
    id integer NOT NULL,
    user_id integer NOT NULL,
    action character varying(50) NOT NULL,
    resource_type character varying(50) NOT NULL,
    resource_id integer,
    description text,
    old_value text,
    new_value text,
    ip_address character varying(50),
    created_at timestamp without time zone
);


ALTER TABLE public.operation_logs OWNER TO postgres;

--
-- Name: operation_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.operation_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.operation_logs_id_seq OWNER TO postgres;

--
-- Name: operation_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.operation_logs_id_seq OWNED BY public.operation_logs.id;


--
-- Name: password_history; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.password_history (
    id integer NOT NULL,
    user_id integer NOT NULL,
    hashed_password character varying(255) NOT NULL,
    created_at timestamp without time zone
);


ALTER TABLE public.password_history OWNER TO postgres;

--
-- Name: password_history_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.password_history_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.password_history_id_seq OWNER TO postgres;

--
-- Name: password_history_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.password_history_id_seq OWNED BY public.password_history.id;


--
-- Name: return_records; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.return_records (
    id integer NOT NULL,
    asset_name character varying NOT NULL,
    employee_id character varying NOT NULL,
    employee_name character varying NOT NULL,
    department character varying,
    return_reason character varying NOT NULL,
    is_returned boolean,
    return_date timestamp without time zone,
    notes text,
    created_at timestamp without time zone
);


ALTER TABLE public.return_records OWNER TO postgres;

--
-- Name: return_records_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.return_records_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.return_records_id_seq OWNER TO postgres;

--
-- Name: return_records_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.return_records_id_seq OWNED BY public.return_records.id;


--
-- Name: users; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.users (
    id integer NOT NULL,
    username character varying(50) NOT NULL,
    email character varying(100),
    hashed_password character varying(255) NOT NULL,
    full_name character varying(100),
    role character varying(20) NOT NULL,
    is_active boolean,
    must_change_password boolean,
    password_changed_at timestamp without time zone,
    last_login timestamp without time zone,
    created_at timestamp without time zone,
    updated_at timestamp without time zone,
    created_by integer
);


ALTER TABLE public.users OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.users_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.users_id_seq OWNER TO postgres;

--
-- Name: users_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.users_id_seq OWNED BY public.users.id;


--
-- Name: warehouse_asset_logs; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.warehouse_asset_logs (
    id integer NOT NULL,
    asset_id integer NOT NULL,
    action character varying NOT NULL,
    description text,
    operator character varying,
    created_at timestamp without time zone
);


ALTER TABLE public.warehouse_asset_logs OWNER TO postgres;

--
-- Name: warehouse_asset_logs_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.warehouse_asset_logs_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.warehouse_asset_logs_id_seq OWNER TO postgres;

--
-- Name: warehouse_asset_logs_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.warehouse_asset_logs_id_seq OWNED BY public.warehouse_asset_logs.id;


--
-- Name: warehouse_assets; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.warehouse_assets (
    id integer NOT NULL,
    name character varying NOT NULL,
    category character varying NOT NULL,
    subcategory character varying,
    brand character varying,
    model character varying,
    receiver_name character varying,
    total_quantity integer,
    available_quantity integer,
    allocated_quantity integer,
    minimum_stock integer,
    location character varying,
    notes text,
    created_at timestamp without time zone,
    updated_at timestamp without time zone
);


ALTER TABLE public.warehouse_assets OWNER TO postgres;

--
-- Name: warehouse_assets_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.warehouse_assets_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.warehouse_assets_id_seq OWNER TO postgres;

--
-- Name: warehouse_assets_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.warehouse_assets_id_seq OWNED BY public.warehouse_assets.id;


--
-- Name: warehouse_locations; Type: TABLE; Schema: public; Owner: postgres
--

CREATE TABLE public.warehouse_locations (
    id integer NOT NULL,
    name character varying NOT NULL,
    description character varying,
    created_at timestamp without time zone
);


ALTER TABLE public.warehouse_locations OWNER TO postgres;

--
-- Name: warehouse_locations_id_seq; Type: SEQUENCE; Schema: public; Owner: postgres
--

CREATE SEQUENCE public.warehouse_locations_id_seq
    AS integer
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


ALTER SEQUENCE public.warehouse_locations_id_seq OWNER TO postgres;

--
-- Name: warehouse_locations_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: postgres
--

ALTER SEQUENCE public.warehouse_locations_id_seq OWNED BY public.warehouse_locations.id;


--
-- Name: asset_deletion_records id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.asset_deletion_records ALTER COLUMN id SET DEFAULT nextval('public.asset_deletion_records_id_seq'::regclass);


--
-- Name: asset_logs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.asset_logs ALTER COLUMN id SET DEFAULT nextval('public.asset_logs_id_seq'::regclass);


--
-- Name: asset_part_logs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.asset_part_logs ALTER COLUMN id SET DEFAULT nextval('public.asset_part_logs_id_seq'::regclass);


--
-- Name: assets id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.assets ALTER COLUMN id SET DEFAULT nextval('public.assets_id_seq'::regclass);


--
-- Name: brands id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.brands ALTER COLUMN id SET DEFAULT nextval('public.brands_id_seq'::regclass);


--
-- Name: departments id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.departments ALTER COLUMN id SET DEFAULT nextval('public.departments_id_seq'::regclass);


--
-- Name: hostname_history id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.hostname_history ALTER COLUMN id SET DEFAULT nextval('public.hostname_history_id_seq'::regclass);


--
-- Name: office_locations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.office_locations ALTER COLUMN id SET DEFAULT nextval('public.office_locations_id_seq'::regclass);


--
-- Name: operation_logs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.operation_logs ALTER COLUMN id SET DEFAULT nextval('public.operation_logs_id_seq'::regclass);


--
-- Name: password_history id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.password_history ALTER COLUMN id SET DEFAULT nextval('public.password_history_id_seq'::regclass);


--
-- Name: return_records id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.return_records ALTER COLUMN id SET DEFAULT nextval('public.return_records_id_seq'::regclass);


--
-- Name: users id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users ALTER COLUMN id SET DEFAULT nextval('public.users_id_seq'::regclass);


--
-- Name: warehouse_asset_logs id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warehouse_asset_logs ALTER COLUMN id SET DEFAULT nextval('public.warehouse_asset_logs_id_seq'::regclass);


--
-- Name: warehouse_assets id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warehouse_assets ALTER COLUMN id SET DEFAULT nextval('public.warehouse_assets_id_seq'::regclass);


--
-- Name: warehouse_locations id; Type: DEFAULT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warehouse_locations ALTER COLUMN id SET DEFAULT nextval('public.warehouse_locations_id_seq'::regclass);


--
-- Data for Name: asset_deletion_records; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.asset_deletion_records (id, asset_id, asset_tag, asset_data, deletion_reason, deleted_by, deleted_at) FROM stdin;
\.


--
-- Data for Name: asset_logs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.asset_logs (id, asset_id, action, description, old_value, new_value, operator, created_at) FROM stdin;
1	1	批量导入	通过 Excel 导入创建资产 ZS-NB26-000001	\N	\N	iris	2026-06-02 10:21:48.294183
2	2	批量导入	通过 Excel 导入创建资产 ZS-NB26-000002	\N	\N	iris	2026-06-02 10:21:48.311714
3	3	批量导入	通过 Excel 导入创建资产 ZS-NB26-000003	\N	\N	iris	2026-06-02 10:21:48.326141
4	4	批量导入	通过 Excel 导入创建资产 ZS-NB26-000004	\N	\N	iris	2026-06-02 10:21:48.326141
5	5	批量导入	通过 Excel 导入创建资产 ZS-NB26-000005	\N	\N	iris	2026-06-02 10:21:48.342414
6	6	批量导入	通过 Excel 导入创建资产 ZS-NB26-000006	\N	\N	iris	2026-06-02 10:21:48.358385
7	7	批量导入	通过 Excel 导入创建资产 ZS-NB26-000007	\N	\N	iris	2026-06-02 10:21:48.358385
8	8	批量导入	通过 Excel 导入创建资产 ZS-NB26-000008	\N	\N	iris	2026-06-02 10:21:48.37465
9	9	批量导入	通过 Excel 导入创建资产 ZS-NB26-000009	\N	\N	iris	2026-06-02 10:21:48.37465
10	10	批量导入	通过 Excel 导入创建资产 ZS-NB26-000010	\N	\N	iris	2026-06-02 10:21:48.391152
11	11	批量导入	通过 Excel 导入创建资产 ZS-PC26-000001	\N	\N	iris	2026-06-02 10:21:48.391557
12	12	批量导入	通过 Excel 导入创建资产 ZS-PC26-000002	\N	\N	iris	2026-06-02 10:21:48.407784
13	13	批量导入	通过 Excel 导入创建资产 ZS-PC26-000003	\N	\N	iris	2026-06-02 10:21:48.409795
14	14	批量导入	通过 Excel 导入创建资产 ZS-PC26-000004	\N	\N	iris	2026-06-02 10:21:48.409795
15	15	批量导入	通过 Excel 导入创建资产 ZS-PC26-000005	\N	\N	iris	2026-06-02 10:21:48.424946
16	16	批量导入	通过 Excel 导入创建资产 ZS-PC26-000006	\N	\N	iris	2026-06-02 10:21:48.424946
17	17	批量导入	通过 Excel 导入创建资产 ZS-PC26-000007	\N	\N	iris	2026-06-02 10:21:48.440059
18	18	批量导入	通过 Excel 导入创建资产 ZS-PC26-000008	\N	\N	iris	2026-06-02 10:21:48.440059
19	19	批量导入	通过 Excel 导入创建资产 ZS-PC26-000009	\N	\N	iris	2026-06-02 10:21:48.455956
20	20	批量导入	通过 Excel 导入创建资产 ZS-PC26-000010	\N	\N	iris	2026-06-02 10:21:48.459221
21	21	批量导入	通过 Excel 导入创建资产 ZS-PD26-000001	\N	\N	iris	2026-06-02 10:21:48.476284
22	22	批量导入	通过 Excel 导入创建资产 ZS-PD26-000002	\N	\N	iris	2026-06-02 10:21:48.476284
23	23	批量导入	通过 Excel 导入创建资产 ZS-PD26-000003	\N	\N	iris	2026-06-02 10:21:48.49162
24	24	批量导入	通过 Excel 导入创建资产 ZS-PD26-000004	\N	\N	iris	2026-06-02 10:21:48.49162
25	25	批量导入	通过 Excel 导入创建资产 ZS-PD26-000005	\N	\N	iris	2026-06-02 10:21:48.509635
26	26	批量导入	通过 Excel 导入创建资产 ZS-MR26-000001	\N	\N	iris	2026-06-02 10:21:48.509635
27	27	批量导入	通过 Excel 导入创建资产 ZS-MR26-000002	\N	\N	iris	2026-06-02 10:21:48.509635
28	28	批量导入	通过 Excel 导入创建资产 ZS-MR26-000003	\N	\N	iris	2026-06-02 10:21:48.52509
29	29	批量导入	通过 Excel 导入创建资产 ZS-MR26-000004	\N	\N	iris	2026-06-02 10:21:48.527049
30	30	批量导入	通过 Excel 导入创建资产 ZS-MR26-000005	\N	\N	iris	2026-06-02 10:21:48.527049
31	1	update	BIOS密码: False → True; TPM状态: False → True; 是否有台式机: False → True	{"BIOS密码": "False", "TPM状态": "False", "是否有台式机": "False"}	{"BIOS密码": "True", "TPM状态": "True", "是否有台式机": "True"}	iris	2026-06-02 10:31:00.155552
32	1	状态变更: 使用中 → 闲置	状态: 使用中 → 闲置; 备注: WIN10 → (空)	{"状态": "使用中", "备注": "WIN10"}	{"状态": "闲置", "备注": "(空)"}	iris	2026-06-02 10:31:10.096483
33	1	update	备注: (空) → test; condition: 可用 → 损坏	{"备注": "(空)", "condition": "可用"}	{"备注": "test", "condition": "损坏"}	iris	2026-06-02 10:31:34.775271
34	1	状态变更: 闲置 → 报废	状态: 闲置 → 报废; 备注: test → 报废原因: test; 工号: E02531 → (空); 使用人: Davy → (空); 部门: CY-拉晶 → (空)	{"状态": "闲置", "备注": "test", "工号": "E02531", "使用人": "Davy", "部门": "CY-拉晶"}	{"状态": "报废", "备注": "报废原因: test", "工号": "(空)", "使用人": "(空)", "部门": "(空)"}	系统管理员	2026-06-02 10:32:31.271628
35	12	update	部门: ACC-财务 → ACC-财务与会计	{"部门": "ACC-财务"}	{"部门": "ACC-财务与会计"}	系统管理员	2026-06-02 10:34:54.40276
36	11	update	备注: WIN10 → (空); 部门: IT-MES → IT-信息技术; 系统版本: 亚信 → WIN10; 杀毒软件: 没锁 → 亚信	{"备注": "WIN10", "部门": "IT-MES", "系统版本": "亚信", "杀毒软件": "没锁"}	{"备注": "(空)", "部门": "IT-信息技术", "系统版本": "WIN10", "杀毒软件": "亚信"}	系统管理员	2026-06-02 10:36:40.021661
37	11	配件新增	新增配件「联想16G内存条DDR5 Lenovo DDR5 16G 4800MHz」× 1	\N	\N	系统管理员	2026-06-02 10:36:50.515776
38	31	创建资产	新建资产 ZS-PC26-000011，品类: 台式机，状态: 闲置	\N	\N	系统管理员	2026-06-02 10:55:51.670037
39	32	创建资产	新建资产 ZS-PC26-000012，品类: 台式机，状态: 闲置	\N	\N	系统管理员	2026-06-02 10:55:51.686541
40	33	创建资产	新建资产 ZS-PC26-000013，品类: 台式机，状态: 闲置	\N	\N	系统管理员	2026-06-02 10:55:51.700072
41	34	创建资产	新建资产 ZS-PC26-000014，品类: 台式机，状态: 闲置	\N	\N	系统管理员	2026-06-02 10:55:51.71338
42	35	创建资产	新建资产 ZS-PC26-000015，品类: 台式机，状态: 闲置	\N	\N	系统管理员	2026-06-02 10:55:51.714416
43	36	创建资产	新建资产 ZS-PC26-000016，品类: 台式机，状态: 闲置	\N	\N	系统管理员	2026-06-02 10:55:51.730214
44	37	创建资产	新建资产 ZS-PC26-000017，品类: 台式机，状态: 闲置	\N	\N	系统管理员	2026-06-02 10:55:51.746499
45	38	创建资产	新建资产 ZS-PC26-000018，品类: 台式机，状态: 闲置	\N	\N	系统管理员	2026-06-02 10:55:51.746499
46	39	创建资产	新建资产 ZS-PC26-000019，品类: 台式机，状态: 闲置	\N	\N	系统管理员	2026-06-02 10:55:51.763911
47	40	创建资产	新建资产 ZS-PC26-000020，品类: 台式机，状态: 闲置	\N	\N	系统管理员	2026-06-02 10:55:51.78054
48	31	update	资产名: (空) → ZS-PC26-000011	{"资产名": "(空)"}	{"资产名": "ZS-PC26-000011"}	系统管理员	2026-06-02 10:56:32.70472
49	31	状态变更: 闲置 → 使用中	状态: 闲置 → 使用中; 使用人: (空) → test; 部门: (空) → IT-信息技术; 资产名: ZS-PC26-000011 → 1ITW0009; 系统版本: (空) → WIN11; 位置: (空) → OA; issue_date: (空) → 2026-06-02 10:58:01.192785	{"状态": "闲置", "使用人": "(空)", "部门": "(空)", "资产名": "ZS-PC26-000011", "系统版本": "(空)", "位置": "(空)", "issue_date": "(空)"}	{"状态": "使用中", "使用人": "test", "部门": "IT-信息技术", "资产名": "1ITW0009", "系统版本": "WIN11", "位置": "OA", "issue_date": "2026-06-02 10:58:01.192785"}	系统管理员	2026-06-02 10:58:01.211122
50	31	状态变更: 使用中 → 闲置	归还处理联动：归还记录 #1，资产状态变更为闲置	\N	\N	系统管理员	2026-06-02 10:59:50.945571
51	41	创建资产	新建资产 ZS-NB26-000011，品类: 笔记本电脑，状态: 闲置	\N	\N	系统管理员	2026-06-02 11:03:39.233189
52	42	创建资产	新建资产 ZS-NB26-000012，品类: 笔记本电脑，状态: 闲置	\N	\N	系统管理员	2026-06-02 11:03:39.248506
53	43	创建资产	新建资产 ZS-NB26-000013，品类: 笔记本电脑，状态: 闲置	\N	\N	系统管理员	2026-06-02 11:03:39.264641
54	44	创建资产	新建资产 ZS-NB26-000014，品类: 笔记本电脑，状态: 闲置	\N	\N	系统管理员	2026-06-02 11:03:39.281735
55	45	创建资产	新建资产 ZS-NB26-000015，品类: 笔记本电脑，状态: 闲置	\N	\N	系统管理员	2026-06-02 11:03:39.297741
56	46	创建资产	新建资产 ZS-NB26-000016，品类: 笔记本电脑，状态: 闲置	\N	\N	系统管理员	2026-06-02 11:03:39.314292
57	2	状态变更: 使用中 → 闲置	状态: 使用中 → 闲置; 备注: WIN10 → 1; 工号: M4专用 → (空); 使用人: M4专用 → (空); 部门: WF-硅片 → (空); 位置: OA → IT库房	{"状态": "使用中", "备注": "WIN10", "工号": "M4专用", "使用人": "M4专用", "部门": "WF-硅片", "位置": "OA"}	{"状态": "闲置", "备注": "1", "工号": "(空)", "使用人": "(空)", "部门": "(空)", "位置": "IT库房"}	系统管理员	2026-06-02 13:16:04.470605
58	2	update	备注: 1 → 2	{"备注": "1"}	{"备注": "2"}	系统管理员	2026-06-02 13:16:13.719977
59	9	update	是否有台式机: False → True	{"是否有台式机": "False"}	{"是否有台式机": "True"}	系统管理员	2026-06-02 14:13:43.656981
60	9	update	备注: WIN10 → (空); 系统版本: EDR → WIN10; 杀毒软件: (空) → EDR	{"备注": "WIN10", "系统版本": "EDR", "杀毒软件": "(空)"}	{"备注": "(空)", "系统版本": "WIN10", "杀毒软件": "EDR"}	系统管理员	2026-06-02 14:58:39.345239
\.


--
-- Data for Name: asset_part_logs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.asset_part_logs (id, asset_id, warehouse_item_id, warehouse_item_name, action, quantity, notes, operator, created_at) FROM stdin;
1	11	2	联想16G内存条DDR5 Lenovo DDR5 16G 4800MHz	新增	1	\N	系统管理员	2026-06-02 10:36:50.497637
\.


--
-- Data for Name: assets; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.assets (id, asset_tag, category, brand, model, serial_number, status, purchase_date, notes, employee_id, employee_name, department, hostname, mac_address, ip_address, fixed_asset_number, system_version, antivirus_software, issue_date, lock_number, supervisor, location, po_number, condition, bios_password, tpm_status, has_desktop, quantity, additional_info, from_warehouse, created_at, updated_at, is_deleted, deleted_at) FROM stdin;
3	ZS-NB26-000003	笔记本电脑	HUAWEI	Huawei Matebook X 2021	H5KPM21B23001363	使用中	\N	WIN10	E02463	matt	FAE-工程应用	SHMSNB311	BC-17-B8-4F-5D-62	\N	A010010337-202207007	EDR	\N	\N	冯天	\N	OA	12000100	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.326141	2026-06-02 10:21:48.326141	f	\N
4	ZS-NB26-000004	笔记本电脑	HUAWEI	Huawei Matebook B5-430 16G	V2NPM22207000864	使用中	\N	WIN10	E02082	孙飞	EPI-外延	SHMSNB243	A0-E7-0B-68-EB-0B	\N	\N	EDR	\N	\N	张斌	\N	OA	12000100	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.326141	2026-06-02 10:21:48.326141	f	\N
5	ZS-NB26-000005	笔记本电脑	Lenovo	ThinkPad X395	PC1HHMJ4	使用中	\N	WIN10	E01563	安然	LC-产线控制	SHMSNB167	3C-58-C2-C7-34-E0	\N	\N	EDR	\N	\N	陈晓春	\N	OA	12000100	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.342414	2026-06-02 10:21:48.342414	f	\N
6	ZS-NB26-000006	笔记本电脑	HUAWEI	Huawei MateBook 14 2019	V4FBB20604800265	使用中	\N	WIN10	采购公用电脑	采购公用电脑	PROC-采购	SHMSNB107	28-7F-CF-A1-9C-21	\N	\N	EDR	\N	\N	刘大海	\N	OA	12000100	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.342414	2026-06-02 10:21:48.342414	f	\N
7	ZS-NB26-000007	笔记本电脑	Lenovo	ThinkPad L14 Gen 1	PF2T26MW	使用中	\N	WIN10	采购公用电脑	采购公用电脑	PROC-采购	SHMSNB180	74-4C-A1-B2-E2-75	\N	A010010271（3）	EDR	\N	\N	刘大海	\N	OA	12000100	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.358385	2026-06-02 10:21:48.358385	f	\N
8	ZS-NB26-000008	笔记本电脑	HUAWEI	Huawei Matebook B5-430	Y9XPM22107001080	使用中	\N	WIN10	E00490	蔡杰	PC-生产控制	SHMSNB263	A8-64-F1-DE-36-09	\N	\N	EDR	\N	\N	蔡杰	\N	OA	12000100	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.358385	2026-06-02 10:21:48.358385	f	\N
10	ZS-NB26-000010	笔记本电脑	HUAWEI	Huawei Matebook B5-430	Y9XPM22107000776	使用中	\N	WIN10	E01268	陈爱琳	PR-公共关系	SHMSNB265	A8-64-F1-DC-36-1F	\N	A010010321-202207001	EDR	\N	\N	李宏	\N	OA	12000200	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.37465	2026-06-02 10:21:48.37465	f	\N
13	ZS-PC26-000003	台式机	HP	HP 280 Pro G2 MT	6CR71929R2	使用中	\N	WIN10	MIS库房	MIS库房	IT-MIS	1ACC0954A	A0-8C-FD-F4-C5-99	\N	A05030169	亚信	没锁	\N	\N	\N	L3	12000200	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.409795	2026-06-02 10:21:48.409795	f	\N
14	ZS-PC26-000004	台式机	HP	HP-elitedesk	4CV946WK7S	使用中	\N	WIN10	E00611	疏敏	ACC-财务	1ACC0611B	84-A9-3E-76-1E-82	\N	A010010226(4)	EDR	ACC-2	\N	\N	\N	L3	12000200	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.409795	2026-06-02 10:21:48.409795	f	\N
15	ZS-PC26-000005	台式机	Lenovo	ThinkCentre K70	YLX1EJZN	使用中	\N	WIN10	E01412	王方丹	ACC-财务	1ACC1412	A4-AE-12-82-B6-5D	\N	A010010254(15)	EDR	没锁	\N	\N	\N	L1	12000200	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.424946	2026-06-02 10:21:48.424946	f	\N
16	ZS-PC26-000006	台式机	Lenovo	ThinkCentre K70	YLX1WMSA	使用中	\N	WIN10	MIS库房	MIS库房	IT-MIS	1CEO0471A	F4-6B-8C-02-54-E3	\N	A010010276(4)	亚信	1CEO0471A	\N	\N	\N	L1	12000200	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.424946	2026-06-02 10:21:48.424946	f	\N
17	ZS-PC26-000007	台式机	HP	HP 280 Pro G3 MT	8CG93955GV	使用中	\N	WIN10	MIS库房	MIS库房	IT-MIS	1CY1849	04-0E-3C-10-1B-7A	\N	A010010220(3)	亚信	1CY1849	\N	\N	\N	L1	12000200	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.440059	2026-06-02 10:21:48.440059	f	\N
18	ZS-PC26-000008	台式机	Lenovo	ThinkCentre K70	YLX21XM3	使用中	\N	WIN10	E01793	王华杰	RD-外延研发	1RD1793	F4-6B-8C-5B-39-1F	\N	无资产标签	EDR	1OP1793	\N	\N	\N	L2	12000200	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.440059	2026-06-02 10:21:48.440059	f	\N
19	ZS-PC26-000009	台式机	HP	HP 280 Pro G1 MT	6CR5398XC4	闲置	\N	WIN10	MIS库房	MIS库房	IT-MIS	1OP1446	50-65-F3-24-D9-45	\N	14.2.1031.0100	亚信	没锁	\N	\N	\N	L2	12000200	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.440059	2026-06-02 10:21:48.440059	f	\N
20	ZS-PC26-000010	台式机	HP	HP 280 Pro G3 MT	4CE8243CVK	闲置	\N	WIN10	MIS库房	MIS库房	IT-MIS	1OP0716	10-E7-C6-1C-9D-C1	\N	12.1.6318.6100	亚信	没锁	\N	\N	\N	L3	12000200	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.459221	2026-06-02 10:21:48.459221	f	\N
21	ZS-PD26-000001	移动设备	HUAWEI	华为平板 M5 青春版	GHR9X19319001520	使用中	\N	\N	E00652	王道平	WF-M3	M3_PAD_01	34-29-12-1A-B9-80	\N	M3_01	\N	\N	\N	\N	\N	\N	\N	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.476284	2026-06-02 10:21:48.476284	f	\N
22	ZS-PD26-000002	移动设备	HUAWEI	华为平板 M5 青春版	GHR9X19319001446	使用中	\N	\N	E00289	蒋广平	WF-M5	M5_PAD_01	34-29-12-1A-B8-EC	\N	M5_01	\N	\N	\N	\N	\N	\N	\N	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.476284	2026-06-02 10:21:48.476284	f	\N
23	ZS-PD26-000003	移动设备	HONOR	荣耀畅玩平板2	FBD4T19327002228	使用中	\N	\N	E00541	李新峰	PC-仓储部	PC_PAD_01	88-BF-E4-42-E7-11	\N	PC_01	\N	\N	\N	\N	\N	\N	\N	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.49162	2026-06-02 10:21:48.49162	f	\N
24	ZS-PD26-000004	移动设备	HUAWEI	华为平板 M5 青春版	GHR9X19826000202	闲置	\N	\N	E00894	魏春雷	IT-MES	IT_PAD_01	DC-16-B2-96-79-06	\N	IT_01	\N	\N	\N	\N	\N	\N	\N	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.49162	2026-06-02 10:21:48.49162	f	\N
25	ZS-PD26-000005	移动设备	HUAWEI	华为平板 M5 青春版	GHR9X19826000327	使用中	\N	\N	E00274	蓝元柯	QA-LAB	LAB_PAD_01	DC-16-B2-96-7A-00	\N	LAB_01	\N	\N	\N	\N	\N	\N	\N	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.49162	2026-06-02 10:21:48.49162	f	\N
26	ZS-MR26-000001	显示器	HP	Series 3 Pro 23.8 英寸 FHD 显示器 - 324pv	\N	使用中	\N	\N	E01252	芦静文	SQA-供应商管理	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.509635	2026-06-02 10:21:48.509635	f	\N
27	ZS-MR26-000002	显示器	HP	Series 3 Pro 23.8 英寸 FHD 显示器 - 324pv	\N	使用中	\N	\N	E01581	范海华	FAC-机械	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.509635	2026-06-02 10:21:48.509635	f	\N
28	ZS-MR26-000003	显示器	HP	Series 3 Pro 23.8 英寸 FHD 显示器 - 324pv	\N	使用中	\N	\N	E01928	郑猛	EHS-公安环保	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.509635	2026-06-02 10:21:48.509635	f	\N
29	ZS-MR26-000004	显示器	HP	Series 3 Pro 23.8 英寸 FHD 显示器 - 324pv	\N	使用中	\N	\N	E03740	王义苹	WF-成型工艺	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.527049	2026-06-02 10:21:48.527049	f	\N
30	ZS-MR26-000005	显示器	HP	Series 3 Pro 23.8 英寸 FHD 显示器 - 324pv	\N	使用中	\N	\N	E03741	顾宇阳	WF-成型工艺	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.527049	2026-06-02 10:21:48.527049	f	\N
12	ZS-PC26-000002	台式机	HP	HP 280 Pro G4 SFF Business PC	4CE8273JV4	使用中	\N	WIN10	财务公用	财务公用	ACC-财务与会计	1ACCPUB01	10-E7-C6-24-05-0F		A010010149	亚信	没锁	\N			OA	12000200	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.391557	2026-06-02 10:34:54.391066	f	\N
1	ZS-NB26-000001	笔记本电脑	HUAWEI	Huawei Matebook B5-430	Y9XPM21C11001137	报废	\N	报废原因: test				L1MSNB001	f4-b3-01-a0-d5-70		A010010338-202207029	EDR		\N	顾问1		OA	12000100	损坏	t	t	t	1	\N	f	2026-06-02 10:21:48.277486	2026-06-02 10:32:31.260183	f	\N
11	ZS-PC26-000001	台式机	HP	HP 280 Pro G2 MT	6CR71929QX	使用中	\N		E00102	姜兰	IT-信息技术	1IT0102L	A0-8C-FD-F4-C5-9E		A010010050(13)	WIN10	亚信	\N			OA	12000200	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.391557	2026-06-02 10:36:40.021661	f	\N
32	ZS-PC26-000012	台式机	HP	HP Pro 280 G9 E PCI	4CE611B2Z0	闲置	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	12000300	可用	f	f	f	1	null	f	2026-06-02 10:55:51.685542	2026-06-02 10:55:51.685542	f	\N
33	ZS-PC26-000013	台式机	HP	HP Pro 280 G9 E PCI	4CE611B2XT	闲置	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	12000300	可用	f	f	f	1	null	f	2026-06-02 10:55:51.699074	2026-06-02 10:55:51.699074	f	\N
34	ZS-PC26-000014	台式机	HP	HP Pro 280 G9 E PCI	4CE611B2ZX	闲置	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	12000300	可用	f	f	f	1	null	f	2026-06-02 10:55:51.712246	2026-06-02 10:55:51.712246	f	\N
2	ZS-NB26-000002	笔记本电脑	Lenovo	ThinkPad S2 2nd Gen	LR0ALNK1	闲置	\N	2				SHMSNB78	B4-D5-BD-B1-6E-3F	\N	A010010191	EDR	\N	\N	史红涛	\N	IT库房	12000100	可用	f	f	f	1	\N	f	2026-06-02 10:21:48.311714	2026-06-02 13:16:13.718531	f	\N
9	ZS-NB26-000009	笔记本电脑	Lenovo	ThinkPad X13 Gen 1	PC28V4H0	使用中	\N		E00062	曹共柏	RD-研发	SHMSNB225	4C-D5-77-B7-2A-07		\N	WIN10	EDR	\N	Danny		OA	12000100	可用	f	f	t	1	\N	f	2026-06-02 10:21:48.37465	2026-06-02 14:58:39.334815	f	\N
35	ZS-PC26-000015	台式机	HP	HP Pro 280 G9 E PCI	4CE611B2ZZ	闲置	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	12000300	可用	f	f	f	1	null	f	2026-06-02 10:55:51.714416	2026-06-02 10:55:51.714416	f	\N
40	ZS-PC26-000020	台式机	HP	HP Pro 280 G9 E PCI	4CE611B2Y9	闲置	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	12000300	可用	f	f	f	1	null	f	2026-06-02 10:55:51.78054	2026-06-02 10:55:51.78054	f	\N
41	ZS-NB26-000011	笔记本电脑	Huawei	荣耀X14 PLUS	AMHMBB12800346	闲置	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	12000400	可用	f	f	f	1	null	f	2026-06-02 11:03:39.233189	2026-06-02 11:03:39.233189	f	\N
46	ZS-NB26-000016	笔记本电脑	Huawei	荣耀X14 PLUS	AMHMBB12800181	闲置	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	12000400	可用	f	f	f	1	null	f	2026-06-02 11:03:39.314292	2026-06-02 11:03:39.314292	f	\N
36	ZS-PC26-000016	台式机	HP	HP Pro 280 G9 E PCI	4CE611B2YK	闲置	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	12000300	可用	f	f	f	1	null	f	2026-06-02 10:55:51.730214	2026-06-02 10:55:51.730214	f	\N
37	ZS-PC26-000017	台式机	HP	HP Pro 280 G9 E PCI	4CE611B2Y6	闲置	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	12000300	可用	f	f	f	1	null	f	2026-06-02 10:55:51.746499	2026-06-02 10:55:51.746499	f	\N
43	ZS-NB26-000013	笔记本电脑	Huawei	荣耀X14 PLUS	AMHMBB2800283	闲置	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	12000400	可用	f	f	f	1	null	f	2026-06-02 11:03:39.264641	2026-06-02 11:03:39.264641	f	\N
38	ZS-PC26-000018	台式机	HP	HP Pro 280 G9 E PCI	4CE611B2VG	闲置	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	12000300	可用	f	f	f	1	null	f	2026-06-02 10:55:51.746499	2026-06-02 10:55:51.746499	f	\N
45	ZS-NB26-000015	笔记本电脑	Huawei	荣耀X14 PLUS	AMHMBB12800058	闲置	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	12000400	可用	f	f	f	1	null	f	2026-06-02 11:03:39.297741	2026-06-02 11:03:39.297741	f	\N
39	ZS-PC26-000019	台式机	HP	HP Pro 280 G9 E PCI	4CE611B2VS	闲置	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	12000300	可用	f	f	f	1	null	f	2026-06-02 10:55:51.763911	2026-06-02 10:55:51.763911	f	\N
31	ZS-PC26-000011	台式机	HP	HP Pro 280 G9 E PCI	4CE611B2Z6	闲置	\N		\N	\N	\N	1ITW0009			\N	WIN11		\N		\N	OA	12000300	可用	f	f	f	1	null	f	2026-06-02 10:55:51.663825	2026-06-02 10:59:50.929546	f	\N
42	ZS-NB26-000012	笔记本电脑	Huawei	荣耀X14 PLUS	AMHMBB12800422	闲置	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	12000400	可用	f	f	f	1	null	f	2026-06-02 11:03:39.248506	2026-06-02 11:03:39.248506	f	\N
44	ZS-NB26-000014	笔记本电脑	Huawei	荣耀X14 PLUS	AMHMBB12800147	闲置	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	\N	12000400	可用	f	f	f	1	null	f	2026-06-02 11:03:39.281735	2026-06-02 11:03:39.281735	f	\N
\.


--
-- Data for Name: brands; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.brands (id, name, created_at) FROM stdin;
1	ASUS	2026-06-02 09:57:27.57764
2	Acer	2026-06-02 09:57:27.57764
3	Apple	2026-06-02 09:57:27.57764
4	Dell	2026-06-02 09:57:27.57764
5	HP	2026-06-02 09:57:27.57764
6	Huawei	2026-06-02 09:57:27.57764
7	Lenovo	2026-06-02 09:57:27.57764
8	Microsoft	2026-06-02 09:57:27.57764
9	Samsung	2026-06-02 09:57:27.57764
10	ThinkPad	2026-06-02 09:57:27.57764
11	Xiaomi	2026-06-02 09:57:27.57764
\.


--
-- Data for Name: departments; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.departments (id, name, parent_id, created_at) FROM stdin;
1	IT-信息技术	\N	2026-06-02 10:34:09.001199
2	HR-人力资源	\N	2026-06-02 10:34:13.648401
3	ACC-财务与会计	\N	2026-06-02 10:34:19.249754
\.


--
-- Data for Name: hostname_history; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.hostname_history (id, asset_id, old_hostname, new_hostname, change_reason, changed_at) FROM stdin;
1	31	\N	ZS-PC26-000011	资产名变更	2026-06-02 10:56:32.70472
2	31	ZS-PC26-000011	1ITW0009	资产名变更	2026-06-02 10:58:01.202599
\.


--
-- Data for Name: office_locations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.office_locations (id, name, description) FROM stdin;
1	L1	1号楼车间
2	L2	5厂车间
3	OA	办公室
4	L3	3厂车间
\.


--
-- Data for Name: operation_logs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.operation_logs (id, user_id, action, resource_type, resource_id, description, old_value, new_value, ip_address, created_at) FROM stdin;
1	1	create	user	2	创建用户: iris	\N	\N	\N	2026-06-02 10:12:42.705599
2	2	login	user	2	用户登录	\N	\N	127.0.0.1	2026-06-02 10:12:53.415705
3	2	change_password	user	2	修改密码	\N	\N	\N	2026-06-02 10:13:04.832857
4	2	import	asset	\N	批量导入资产，成功写入 30 条	\N	\N	\N	2026-06-02 10:21:48.527049
5	2	update	asset	1	BIOS密码: False → True; TPM状态: False → True; 是否有台式机: False → True	{"BIOS密码": "False", "TPM状态": "False", "是否有台式机": "False"}	{"BIOS密码": "True", "TPM状态": "True", "是否有台式机": "True"}	\N	2026-06-02 10:31:00.15824
6	2	update	asset	1	状态: 使用中 → 闲置; 备注: WIN10 → (空)	{"状态": "使用中", "备注": "WIN10"}	{"状态": "闲置", "备注": "(空)"}	\N	2026-06-02 10:31:10.10679
7	2	update	asset	1	备注: (空) → test; condition: 可用 → 损坏	{"备注": "(空)", "condition": "可用"}	{"备注": "test", "condition": "损坏"}	\N	2026-06-02 10:31:34.780228
8	1	login	user	1	用户登录	\N	\N	127.0.0.1	2026-06-02 10:32:04.745832
9	1	update	asset	1	状态: 闲置 → 报废; 备注: test → 报废原因: test; 工号: E02531 → (空); 使用人: Davy → (空); 部门: CY-拉晶 → (空)	{"状态": "闲置", "备注": "test", "工号": "E02531", "使用人": "Davy", "部门": "CY-拉晶"}	{"状态": "报废", "备注": "报废原因: test", "工号": "(空)", "使用人": "(空)", "部门": "(空)"}	\N	2026-06-02 10:32:31.275459
10	1	update	asset	12	部门: ACC-财务 → ACC-财务与会计	{"部门": "ACC-财务"}	{"部门": "ACC-财务与会计"}	\N	2026-06-02 10:34:54.408378
11	1	update	asset	11	备注: WIN10 → (空); 部门: IT-MES → IT-信息技术; 系统版本: 亚信 → WIN10; 杀毒软件: 没锁 → 亚信	{"备注": "WIN10", "部门": "IT-MES", "系统版本": "亚信", "杀毒软件": "没锁"}	{"备注": "(空)", "部门": "IT-信息技术", "系统版本": "WIN10", "杀毒软件": "亚信"}	\N	2026-06-02 10:36:40.021661
12	1	create	asset	31	新建资产 ZS-PC26-000011，品类: 台式机，状态: 闲置	\N	\N	\N	2026-06-02 10:55:51.671035
13	1	create	asset	32	新建资产 ZS-PC26-000012，品类: 台式机，状态: 闲置	\N	\N	\N	2026-06-02 10:55:51.687542
14	1	create	asset	33	新建资产 ZS-PC26-000013，品类: 台式机，状态: 闲置	\N	\N	\N	2026-06-02 10:55:51.701069
15	1	create	asset	34	新建资产 ZS-PC26-000014，品类: 台式机，状态: 闲置	\N	\N	\N	2026-06-02 10:55:51.714416
16	1	create	asset	35	新建资产 ZS-PC26-000015，品类: 台式机，状态: 闲置	\N	\N	\N	2026-06-02 10:55:51.714416
17	1	create	asset	36	新建资产 ZS-PC26-000016，品类: 台式机，状态: 闲置	\N	\N	\N	2026-06-02 10:55:51.730214
18	1	create	asset	37	新建资产 ZS-PC26-000017，品类: 台式机，状态: 闲置	\N	\N	\N	2026-06-02 10:55:51.746499
19	1	create	asset	38	新建资产 ZS-PC26-000018，品类: 台式机，状态: 闲置	\N	\N	\N	2026-06-02 10:55:51.762234
20	1	create	asset	39	新建资产 ZS-PC26-000019，品类: 台式机，状态: 闲置	\N	\N	\N	2026-06-02 10:55:51.763911
21	1	create	asset	40	新建资产 ZS-PC26-000020，品类: 台式机，状态: 闲置	\N	\N	\N	2026-06-02 10:55:51.78054
22	1	update	asset	31	资产名: (空) → ZS-PC26-000011	{"资产名": "(空)"}	{"资产名": "ZS-PC26-000011"}	\N	2026-06-02 10:56:32.719733
23	1	update	asset	31	状态: 闲置 → 使用中; 使用人: (空) → test; 部门: (空) → IT-信息技术; 资产名: ZS-PC26-000011 → 1ITW0009; 系统版本: (空) → WIN11; 位置: (空) → OA; issue_date: (空) → 2026-06-02 10:58:01.192785	{"状态": "闲置", "使用人": "(空)", "部门": "(空)", "资产名": "ZS-PC26-000011", "系统版本": "(空)", "位置": "(空)", "issue_date": "(空)"}	{"状态": "使用中", "使用人": "test", "部门": "IT-信息技术", "资产名": "1ITW0009", "系统版本": "WIN11", "位置": "OA", "issue_date": "2026-06-02 10:58:01.192785"}	\N	2026-06-02 10:58:01.211122
24	1	update	asset	31	归还处理联动：资产 ZS-PC26-000011 状态变更为闲置	\N	\N	\N	2026-06-02 10:59:50.959251
25	1	create	asset	41	新建资产 ZS-NB26-000011，品类: 笔记本电脑，状态: 闲置	\N	\N	\N	2026-06-02 11:03:39.233189
26	1	create	asset	42	新建资产 ZS-NB26-000012，品类: 笔记本电脑，状态: 闲置	\N	\N	\N	2026-06-02 11:03:39.248506
27	1	create	asset	43	新建资产 ZS-NB26-000013，品类: 笔记本电脑，状态: 闲置	\N	\N	\N	2026-06-02 11:03:39.264641
28	1	create	asset	44	新建资产 ZS-NB26-000014，品类: 笔记本电脑，状态: 闲置	\N	\N	\N	2026-06-02 11:03:39.281735
29	1	create	asset	45	新建资产 ZS-NB26-000015，品类: 笔记本电脑，状态: 闲置	\N	\N	\N	2026-06-02 11:03:39.297741
30	1	create	asset	46	新建资产 ZS-NB26-000016，品类: 笔记本电脑，状态: 闲置	\N	\N	\N	2026-06-02 11:03:39.314292
31	1	login	user	1	用户登录	\N	\N	10.9.60.27	2026-06-02 13:15:02.190149
32	1	update	asset	2	状态: 使用中 → 闲置; 备注: WIN10 → 1; 工号: M4专用 → (空); 使用人: M4专用 → (空); 部门: WF-硅片 → (空); 位置: OA → IT库房	{"状态": "使用中", "备注": "WIN10", "工号": "M4专用", "使用人": "M4专用", "部门": "WF-硅片", "位置": "OA"}	{"状态": "闲置", "备注": "1", "工号": "(空)", "使用人": "(空)", "部门": "(空)", "位置": "IT库房"}	\N	2026-06-02 13:16:04.476118
33	1	update	asset	2	备注: 1 → 2	{"备注": "1"}	{"备注": "2"}	\N	2026-06-02 13:16:13.719977
34	1	login	user	1	用户登录	\N	\N	10.9.120.207	2026-06-02 14:10:40.383993
35	1	update	asset	9	是否有台式机: False → True	{"是否有台式机": "False"}	{"是否有台式机": "True"}	\N	2026-06-02 14:13:43.658963
36	1	login	user	1	用户登录	\N	\N	10.9.120.207	2026-06-02 14:58:01.603453
37	1	update	asset	9	备注: WIN10 → (空); 系统版本: EDR → WIN10; 杀毒软件: (空) → EDR	{"备注": "WIN10", "系统版本": "EDR", "杀毒软件": "(空)"}	{"备注": "(空)", "系统版本": "WIN10", "杀毒软件": "EDR"}	\N	2026-06-02 14:58:39.351116
\.


--
-- Data for Name: password_history; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.password_history (id, user_id, hashed_password, created_at) FROM stdin;
1	2	$2b$12$RFdz/xC06gdDKHKhL5DNkeQ8DP9iQbpnsnyB5jsJLjB8UyiXp6j4O	2026-06-02 10:13:04.816852
\.


--
-- Data for Name: return_records; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.return_records (id, asset_name, employee_id, employee_name, department, return_reason, is_returned, return_date, notes, created_at) FROM stdin;
1	1ITW0009	w0009	test	IT-信息技术	设备更换	t	2026-06-02 08:00:00	\N	2026-06-02 10:59:41.929531
\.


--
-- Data for Name: users; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.users (id, username, email, hashed_password, full_name, role, is_active, must_change_password, password_changed_at, last_login, created_at, updated_at, created_by) FROM stdin;
2	iris	iris@zingsemi.com	$2b$12$j8MeO0GnV1dAhAXM54K7heFbOJuMgaLcJsqKuZ6.cfYgWW2Nxicxq	iris	MIS	t	f	2026-06-02 10:13:04.816852	2026-06-02 10:12:53.39632	2026-06-02 10:12:42.67113	2026-06-02 10:13:04.816852	1
1	admin	admin@zingsemi.com	$2b$12$OjTDybURsdVXa5vzsNML2e3GpuX3B1258RJOVrKfTM1EsNFPCA1e6	系统管理员	admin	t	f	2026-06-02 09:57:17.390666	2026-06-02 14:58:01.603453	2026-06-02 09:57:17.390666	2026-06-02 14:58:01.603453	\N
\.


--
-- Data for Name: warehouse_asset_logs; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.warehouse_asset_logs (id, asset_id, action, description, operator, created_at) FROM stdin;
1	1	入库	新增库房资产: 荣耀无线鼠标，数量: 110	iris	2026-06-02 10:26:14.731501
2	2	入库	新增库房资产: 联想16G内存条DDR5，数量: 10	iris	2026-06-02 10:28:48.674928
3	3	入库	新增库房资产: 23.8寸显示器，数量: 200	iris	2026-06-02 10:29:45.986233
4	2	配件出库（新增）	资产 1IT0102L 新增配件，出库 1 件，剩余可用 9	系统管理员	2026-06-02 10:36:50.50764
\.


--
-- Data for Name: warehouse_assets; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.warehouse_assets (id, name, category, subcategory, brand, model, receiver_name, total_quantity, available_quantity, allocated_quantity, minimum_stock, location, notes, created_at, updated_at) FROM stdin;
1	荣耀无线鼠标	输入设备	蓝牙无线鼠标	Huawei		iris	110	100	10	4	IT库房		2026-06-02 10:26:14.728501	2026-06-02 10:26:14.728501
3	23.8寸显示器	显示设备	联想显示器	Lenovo	Series 3 Pro 23.8 英寸 FHD 显示器 - 324pv	iris	200	200	0	5	IT库房		2026-06-02 10:29:45.97509	2026-06-02 10:29:45.97509
2	联想16G内存条DDR5	其他配件		Lenovo	DDR5 16G 4800MHz	iris	10	9	1	5	IT库房		2026-06-02 10:28:48.674928	2026-06-02 10:36:50.493197
\.


--
-- Data for Name: warehouse_locations; Type: TABLE DATA; Schema: public; Owner: postgres
--

COPY public.warehouse_locations (id, name, description, created_at) FROM stdin;
1	IT库房	\N	2026-06-02 09:57:48.11876
2	A区货架	\N	2026-06-02 09:57:48.11876
3	B区货架	\N	2026-06-02 09:57:48.11876
4	C区货架	\N	2026-06-02 09:57:48.11876
5	临时存放区	\N	2026-06-02 09:57:48.11876
6	办公区域	\N	2026-06-02 09:57:48.11876
\.


--
-- Name: asset_deletion_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.asset_deletion_records_id_seq', 1, false);


--
-- Name: asset_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.asset_logs_id_seq', 60, true);


--
-- Name: asset_part_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.asset_part_logs_id_seq', 1, true);


--
-- Name: assets_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.assets_id_seq', 46, true);


--
-- Name: brands_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.brands_id_seq', 11, true);


--
-- Name: departments_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.departments_id_seq', 3, true);


--
-- Name: hostname_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.hostname_history_id_seq', 2, true);


--
-- Name: office_locations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.office_locations_id_seq', 4, true);


--
-- Name: operation_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.operation_logs_id_seq', 37, true);


--
-- Name: password_history_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.password_history_id_seq', 1, true);


--
-- Name: return_records_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.return_records_id_seq', 1, true);


--
-- Name: users_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.users_id_seq', 2, true);


--
-- Name: warehouse_asset_logs_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.warehouse_asset_logs_id_seq', 4, true);


--
-- Name: warehouse_assets_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.warehouse_assets_id_seq', 3, true);


--
-- Name: warehouse_locations_id_seq; Type: SEQUENCE SET; Schema: public; Owner: postgres
--

SELECT pg_catalog.setval('public.warehouse_locations_id_seq', 6, true);


--
-- Name: asset_deletion_records asset_deletion_records_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.asset_deletion_records
    ADD CONSTRAINT asset_deletion_records_pkey PRIMARY KEY (id);


--
-- Name: asset_logs asset_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.asset_logs
    ADD CONSTRAINT asset_logs_pkey PRIMARY KEY (id);


--
-- Name: asset_part_logs asset_part_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.asset_part_logs
    ADD CONSTRAINT asset_part_logs_pkey PRIMARY KEY (id);


--
-- Name: assets assets_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.assets
    ADD CONSTRAINT assets_pkey PRIMARY KEY (id);


--
-- Name: assets assets_serial_number_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.assets
    ADD CONSTRAINT assets_serial_number_key UNIQUE (serial_number);


--
-- Name: brands brands_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.brands
    ADD CONSTRAINT brands_name_key UNIQUE (name);


--
-- Name: brands brands_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.brands
    ADD CONSTRAINT brands_pkey PRIMARY KEY (id);


--
-- Name: departments departments_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_name_key UNIQUE (name);


--
-- Name: departments departments_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_pkey PRIMARY KEY (id);


--
-- Name: hostname_history hostname_history_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.hostname_history
    ADD CONSTRAINT hostname_history_pkey PRIMARY KEY (id);


--
-- Name: office_locations office_locations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.office_locations
    ADD CONSTRAINT office_locations_pkey PRIMARY KEY (id);


--
-- Name: operation_logs operation_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.operation_logs
    ADD CONSTRAINT operation_logs_pkey PRIMARY KEY (id);


--
-- Name: password_history password_history_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.password_history
    ADD CONSTRAINT password_history_pkey PRIMARY KEY (id);


--
-- Name: return_records return_records_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.return_records
    ADD CONSTRAINT return_records_pkey PRIMARY KEY (id);


--
-- Name: users users_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_pkey PRIMARY KEY (id);


--
-- Name: warehouse_asset_logs warehouse_asset_logs_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warehouse_asset_logs
    ADD CONSTRAINT warehouse_asset_logs_pkey PRIMARY KEY (id);


--
-- Name: warehouse_assets warehouse_assets_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warehouse_assets
    ADD CONSTRAINT warehouse_assets_pkey PRIMARY KEY (id);


--
-- Name: warehouse_locations warehouse_locations_name_key; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warehouse_locations
    ADD CONSTRAINT warehouse_locations_name_key UNIQUE (name);


--
-- Name: warehouse_locations warehouse_locations_pkey; Type: CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warehouse_locations
    ADD CONSTRAINT warehouse_locations_pkey PRIMARY KEY (id);


--
-- Name: ix_asset_deletion_records_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_asset_deletion_records_id ON public.asset_deletion_records USING btree (id);


--
-- Name: ix_asset_logs_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_asset_logs_id ON public.asset_logs USING btree (id);


--
-- Name: ix_asset_part_logs_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_asset_part_logs_id ON public.asset_part_logs USING btree (id);


--
-- Name: ix_assets_asset_tag; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_assets_asset_tag ON public.assets USING btree (asset_tag);


--
-- Name: ix_assets_brand; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_assets_brand ON public.assets USING btree (brand);


--
-- Name: ix_assets_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_assets_category ON public.assets USING btree (category);


--
-- Name: ix_assets_department; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_assets_department ON public.assets USING btree (department);


--
-- Name: ix_assets_employee_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_assets_employee_id ON public.assets USING btree (employee_id);


--
-- Name: ix_assets_employee_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_assets_employee_name ON public.assets USING btree (employee_name);


--
-- Name: ix_assets_fixed_asset_number; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_assets_fixed_asset_number ON public.assets USING btree (fixed_asset_number);


--
-- Name: ix_assets_hostname; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_assets_hostname ON public.assets USING btree (hostname);


--
-- Name: ix_assets_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_assets_id ON public.assets USING btree (id);


--
-- Name: ix_assets_location; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_assets_location ON public.assets USING btree (location);


--
-- Name: ix_assets_model; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_assets_model ON public.assets USING btree (model);


--
-- Name: ix_assets_status; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_assets_status ON public.assets USING btree (status);


--
-- Name: ix_brands_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_brands_id ON public.brands USING btree (id);


--
-- Name: ix_departments_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_departments_id ON public.departments USING btree (id);


--
-- Name: ix_hostname_history_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_hostname_history_id ON public.hostname_history USING btree (id);


--
-- Name: ix_office_locations_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_office_locations_id ON public.office_locations USING btree (id);


--
-- Name: ix_office_locations_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_office_locations_name ON public.office_locations USING btree (name);


--
-- Name: ix_operation_logs_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_operation_logs_id ON public.operation_logs USING btree (id);


--
-- Name: ix_password_history_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_password_history_id ON public.password_history USING btree (id);


--
-- Name: ix_return_records_asset_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_return_records_asset_name ON public.return_records USING btree (asset_name);


--
-- Name: ix_return_records_department; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_return_records_department ON public.return_records USING btree (department);


--
-- Name: ix_return_records_employee_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_return_records_employee_id ON public.return_records USING btree (employee_id);


--
-- Name: ix_return_records_employee_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_return_records_employee_name ON public.return_records USING btree (employee_name);


--
-- Name: ix_return_records_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_return_records_id ON public.return_records USING btree (id);


--
-- Name: ix_users_email; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_users_email ON public.users USING btree (email);


--
-- Name: ix_users_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_users_id ON public.users USING btree (id);


--
-- Name: ix_users_username; Type: INDEX; Schema: public; Owner: postgres
--

CREATE UNIQUE INDEX ix_users_username ON public.users USING btree (username);


--
-- Name: ix_warehouse_asset_logs_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_warehouse_asset_logs_id ON public.warehouse_asset_logs USING btree (id);


--
-- Name: ix_warehouse_assets_brand; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_warehouse_assets_brand ON public.warehouse_assets USING btree (brand);


--
-- Name: ix_warehouse_assets_category; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_warehouse_assets_category ON public.warehouse_assets USING btree (category);


--
-- Name: ix_warehouse_assets_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_warehouse_assets_id ON public.warehouse_assets USING btree (id);


--
-- Name: ix_warehouse_assets_model; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_warehouse_assets_model ON public.warehouse_assets USING btree (model);


--
-- Name: ix_warehouse_assets_name; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_warehouse_assets_name ON public.warehouse_assets USING btree (name);


--
-- Name: ix_warehouse_assets_subcategory; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_warehouse_assets_subcategory ON public.warehouse_assets USING btree (subcategory);


--
-- Name: ix_warehouse_locations_id; Type: INDEX; Schema: public; Owner: postgres
--

CREATE INDEX ix_warehouse_locations_id ON public.warehouse_locations USING btree (id);


--
-- Name: asset_deletion_records asset_deletion_records_deleted_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.asset_deletion_records
    ADD CONSTRAINT asset_deletion_records_deleted_by_fkey FOREIGN KEY (deleted_by) REFERENCES public.users(id);


--
-- Name: asset_logs asset_logs_asset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.asset_logs
    ADD CONSTRAINT asset_logs_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES public.assets(id) ON DELETE SET NULL;


--
-- Name: asset_part_logs asset_part_logs_asset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.asset_part_logs
    ADD CONSTRAINT asset_part_logs_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES public.assets(id) ON DELETE CASCADE;


--
-- Name: asset_part_logs asset_part_logs_warehouse_item_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.asset_part_logs
    ADD CONSTRAINT asset_part_logs_warehouse_item_id_fkey FOREIGN KEY (warehouse_item_id) REFERENCES public.warehouse_assets(id) ON DELETE SET NULL;


--
-- Name: departments departments_parent_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.departments
    ADD CONSTRAINT departments_parent_id_fkey FOREIGN KEY (parent_id) REFERENCES public.departments(id);


--
-- Name: hostname_history hostname_history_asset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.hostname_history
    ADD CONSTRAINT hostname_history_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES public.assets(id);


--
-- Name: operation_logs operation_logs_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.operation_logs
    ADD CONSTRAINT operation_logs_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: password_history password_history_user_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.password_history
    ADD CONSTRAINT password_history_user_id_fkey FOREIGN KEY (user_id) REFERENCES public.users(id);


--
-- Name: users users_created_by_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.users
    ADD CONSTRAINT users_created_by_fkey FOREIGN KEY (created_by) REFERENCES public.users(id);


--
-- Name: warehouse_asset_logs warehouse_asset_logs_asset_id_fkey; Type: FK CONSTRAINT; Schema: public; Owner: postgres
--

ALTER TABLE ONLY public.warehouse_asset_logs
    ADD CONSTRAINT warehouse_asset_logs_asset_id_fkey FOREIGN KEY (asset_id) REFERENCES public.warehouse_assets(id);


--
-- PostgreSQL database dump complete
--

\unrestrict TMF6GmOs4Y2fx8x2fDkv1qs7eLjlzFBEIBz6eUA33Su63w3qv3RR89hhNZ2XBtX

