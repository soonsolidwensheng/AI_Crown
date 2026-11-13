# 26年7月20日更新

`postprocess` 接口的 `get_purue_beiya()`（备牙邻牙边缘处理）中的 `pypruners.pruner` 替换为 CutMeshPython 的轮廓切割算法（`segment_by_contour`）。新增 2 个可选输入参数：

- `control_pts_front`：`(N,3)` 点数组，备牙边缘轮廓坐标。传入时启用新版切割：CutMeshPython 沿此轮廓切割 `mesh_jaw`，自动选取顶点数最接近原 `mesh_beiya` 的连通体作为新的 `mesh_beiya`。**不传或传空则跳过切割**，直接使用传入的 `mesh_beiya`（与旧版行为一致）。切割失败时打印警告日志并回退使用原始传入的 `mesh_beiya`。
- `cement_gap`：float，默认 `0.12`。粘结剂缝隙大小（mm），从原来的固定默认值改为顶层可配置参数，覆盖 `paras` 内的同名参数。

## postprocess / stitch_edge

两个接口均支持，新增输入参数相同：

```json
{
    // ...之前的参数
    "control_pts_front": "array",     // 可选，(N,3)备牙边缘轮廓点。传入时启用CutMeshPython轮廓切割，不传、null或空数组时跳过切割
    "cement_gap": "float",            // 可选，默认0.12。粘结剂缝隙大小（mm），覆盖paras内的同名参数
}
```

> 注意：`undercut_filling` 接口已废弃，不再使用。

# 26年7月14日更新

取消7月13日新增的 `margin-align-algorithm-v1` 和 `stitch-algorithm-v-1` 两个 Feature Flag，改为直接固定使用当时 flag=true 对应的新算法，不再需要任何输入参数控制：

- `postprocess` 接口的 trans_neck()：统一使用测地距离环形过渡带变形+咬合面锚点保护算法（旧版简单TPS对齐算法已删除）
- `postprocess`/`stitch_edge` 接口 fill_gap() 内的 occ_id 重算：统一使用测地距离扩张+边界收缩算法（旧版拓扑邻居扩张逻辑已删除）

`margin-align-algorithm-v1` 和 `stitch-algorithm-v-1` 这两个字段不再生效，传了会被忽略。

# 26年7月13日更新

新增2个 Feature Flag，均默认关闭（不传或传 `false` 时行为与之前完全一致），用于灰度验证margin对齐和咬合区域重算的新算法：

- `margin-align-algorithm-v1`：**仅在 `postprocess` 接口生效**（对应 trans_neck()，只在生成外冠后的margin对齐阶段调用一次，`stitch_edge` 接口不会读取这个字段）
- `stitch-algorithm-v-1`：**在 `postprocess` 和 `stitch_edge` 两个接口都生效**（对应 fill_gap() 内部的咬合区域(occ_id)重算逻辑，这两个接口都会调用 fill_gap()）

## postprocess

**输入Input**：

```json
{
    // ...之前的参数
    "margin-align-algorithm-v1": "bool", // 可选，默认false，仅postprocess接口支持。true时启用新版trans_neck()：基于测地距离的环形过渡带变形，并保护咬合面锚点不被移动；false时沿用重构前的简单TPS对齐算法
    "stitch-algorithm-v-1": "bool", // 可选，默认false。true时启用新版咬合区域(occ_id)重算逻辑：基于测地距离扩张后再收缩边界一圈；false时沿用原有的拓扑邻居扩张逻辑
}
```

## stitch_edge

**输入Input**：

```json
{
    // ...之前的参数
    "stitch-algorithm-v-1": "bool", // 可选，默认false，含义同上（stitch_edge接口不支持margin-align-algorithm-v1，该flag只在postprocess生效）
}
```

> 以上2个 flag 已于7月14日取消，详见上方最新更新。

# 26年7月7日更新

1、重构 trans_neck()（备牙边缘对齐算法）：引入测地距离工具函数，在 neck 边缘与咬合面之间构建环形分层过渡带，通过 falloff 加权位移实现自适应变形，同时保护咬合面锚点不受影响。（此算法目前需通过上方的 `margin-align-algorithm-v1` flag 显式开启，默认仍为重构前的旧算法）
2、修复 stitch_() 缝合函数在首轮迭代和边界闭合上的边界条件bug，避免生成重复三角形。


# 26年6月2日更新

1、镜像流程（preop_or_mirror 为 mirror 时）新增补洞修复：在等距重网格化后调用 `meshing_close_holes()`。
2、针对镜像/术前流程（preop_or_mirror 不为空时）对外冠面片新增remesh步骤：非流形边清理、退化三角形/重复顶点清理后，调用 pymeshlab 的等距显式重网格化。
3、外冠面片输出前新增清理逻辑（remove_degenerate_faces 等），减少下游算法处理脏面片的问题。

# 26年6月1日更新

1、修复厚度调整算法（py_minimum_thickness.py）中 Blender 网格转换函数 convertMesh 的重复点问题，改为直接用 `mesh.from_pydata` 构建网格，避免旧版 bmesh 转换流程产生的伪影。
2、外冠面片清理逻辑调整。

# 26年5月26日更新

1、新增非流形网格清理函数 clean_non_manifold_mesh，统一处理重复顶点/三角形、退化三角形、非流形边和非流形顶点，增强网格处理的鲁棒性。
2、get_biggest_mesh 和 slice_mesh 流程新增空网格保护：当输入网格为空、无连通分量、或裁剪/pruner 后结果为空时抛出明确异常，而非静默出错。

# 26年5月18日更新

1、新增安全合并近点算法（safe_merge_close_vertices.py），替换原有的全局近点合并逻辑：合并前检查边界缓冲区（boundary_buffer）和法向夹角阈值（normal_angle_deg），避免跨薄壁、跨折角或跨边界误合并。merge_close_vertices() 内部改为调用该实现。
2、修复镜像流程中 adjust_crown_position()（牙冠与邻牙位置调整）的缩放参数计算错误：多处硬编码的缩放偏移量不一致，统一改为可配置的偏移变量。
3、postprocess.py / stitch_edge.py 内部重构：提取"多重修复逆变换"逻辑（_apply_multi_restoration_inverse_transforms）和 crown 压缩逻辑为独立函数，消除重复代码，接口行为不变。

# 26年5月12日更新
以下接口均已兼容 `source_url` 和 `target_url`：

- `crown_cpu/stdcrown.py`
- `crown_cpu/postprocess.py`
- `crown_cpu/stitch_edge.py`
- `crown_cpu/register_preop_to_postop.py`

调用方式说明：

- 可直接传完整 payload
- 也可只传外层控制字段
- `source_url`：先下载真实输入 JSON
- `target_url`：处理完成后自动上传结果
- 不传 `target_url`：继续直接返回本地结果

```json
{
    "...": "...",
    "source_url": "https://xxx.com/xxx/xxx/input.json",
    "target_url": "https://xxx.com/xxx/xxx/output.json"
}
```

# 26年5月11日更新
crown_cpu/postprocess.py中增加参数：兼容`source_url`和`target_url`，如果有这两个参数，直接从url获取输入
```json
{
    "...": "...",
    "source_url": "https://xxx.com/xxx/xxx/xxx.json",
    "target_url": "https://xxx.com/xxx/xxx/xxx.json",
}
```

# 26年5月9日更新
crown_cpu/stdcrown.py中增加参数：兼容`source_url`和`target_url`，如果有这两个参数，直接从url获取输入
```json
{
    "...": "...",
    "source_url": "https://xxx.com/xxx/xxx/xxx.json",
    "target_url": "https://xxx.com/xxx/xxx/xxx.json",
}
```

# 26年3月10日更新
crown_cpu/test_data中更新测试数据，crown_post.json用于测试post接口，crown_standard.json用于测试stdcrown接口


# 26年2月3日更新
post接口新增3个输出
```json
{   
    // ...之前的参数
    "collides_with_antagonist": "bool",  // 最小厚度外壳是否与对颌碰撞
    "collides_with_adjacent": "bool",    // 最小厚度外壳是否与邻牙碰撞
}
```

# 26年1月4日更新
post接口新增1个输出
```json
{   
    // ...之前的参数
    "warning_info": "bool",  // 镜像流程中是否触发报警
}
```

# 25年11月6日更新
新增register_preop_to_postop接口，在术前流程中得到术前模型匹配术后模型的旋转矩阵，参数如下

**输入**

```json
{   
    "preop_teeth": "dict",  // 术前模型的牙齿分割结果(包括上下颌所有牙齿)
    "postop_teeth": "dict", // 术后模型的牙齿分割结果(包括上下颌所有牙齿)
}
```

该接口当前也支持 URL 方式调用：

```json
{
    "source_url": "https://xxx.com/xxx/xxx/input.json",
    "target_url": "https://xxx.com/xxx/xxx/output.json"
}
```

```json
{
  "preop_to_postop": {
    "upper_matrix": "list", // 4×4矩阵，术前上颌变换至术后位置
    "lower_matrix": "list"  // 4×4矩阵，术前下颌变换至术后位置
  },
  "postop_to_preop": {
    "upper_matrix": "list", // 4×4矩阵，术后上颌变换至术前位置  
    "lower_matrix": "list"  // 4×4矩阵，术后下颌变换至术前位置
  }
}
```

# 25年9月25日更新内容
1、post， stitch接口输出增加self_intersecting（检测生成的牙冠是否有自相交），thick_shell_hit（检测厚度外壳是否和牙冠有碰撞）
2、post，stitch接口输出drc中增加咬合面区域的标识，标识为4
## postprocess

**输出**

```json
{   
    // ...之前的参数
    "self_intersecting": "bool",
    "thick_shell_hit": "bool"
}
```

## stitch_edge

**输出**

```json
{   
    // ...之前的参数
    "self_intersecting": "bool",
    "thick_shell_hit": "bool"
}
```

# 25年9月3日更新内容
术前镜像流程接入，代替之前的stdcrown接口

## stdcrown

**术前输入Input**

```json
{   
    // ...之前的参数
    "preop_or_mirror": "preop", // 表示进行术前流程
    "std_crown": "drc", // gpu输出的初始位置牙冠
    "pre_op_crown": "drc",  // 术前牙冠
    "preop_matrix": "list"  // 术前匹配术后的变换矩阵
    // 删除该参数 "pre_op_teeth": "drc",  // 术前牙颌
}
```

**镜像输入Input**

```json
{   
    // ...之前的参数
    "preop_or_mirror": "mirror", // 表示进行镜像流程
    "std_crown": "drc", // gpu输出的初始位置牙冠
    "mirror_id": "str",  // 镜像位置牙冠id
}
```


# 25年7月24日更新内容
多修复体参数说明，输入根据gpu参数有变化，输出与单修复体一致

## stdcrown

**输入Input**

```json
{   
    "multi_restoration": "int",  // 区分多修复体和单修复体，1表示多修复体，0表示单修复体
    // from gpu final_results
    "mesh_upper": "drc",  // 上颌牙 upper scan
    "mesh_lower": "drc",  // 下颌牙 lower scan
    "mesh_kps": "",  // 关键点信息 key points 
    "all_teeth_seg": "",  // 其他牙齿的 drc 信息 all teeth except for the prep and adjacents
    // from gpu crown_res
    "closer": "drc",  // 近中邻牙 misial adjacent tooth
    "further": "drc",  // 远中邻牙 distal adjacent tooth
    "beiya_id": "str",  // 备牙牙号 tooth number of the prep
    "is_single": "int",  // 单邻牙标志 is the prep only has a single adjacent
    "crown_rot": "list",  // ai变换矩阵
    "pred_filestem_name": "str",  // 模板文件名称
    // from front
    "prep": "drc",  // 备牙 prep tooth
}
```

## postprocess

**输入Input**：

```json
{
    "multi_restoration": "int",  // 区分多修复体和单修复体，1表示多修复体，0表示单修复体
    "cpu_std_json": { /* 之前 CPU 的输出 */ }, // Previous CPU output, P.S. "cpu_undercut_json" secretly works here too
    "standard": "drc",  // 生成牙冠的初始状态，由前端输入 initially placed lib tooth
    "inner": "drc",  // 备牙，由前端输入 the prep
    "paras": {
        "adjust_crown": "int",  //可选，默认值为1。值为0表示不对牙冠做邻接、咬合、厚度调整
    },  // 其他输入参数，如邻牙间隙距离，粘结剂缝隙大小，牙冠厚度等
    "crown_rot_matirx": "array", // 初始位置摆放的旋转矩阵 rotation matrix of the initial placement of the lib tooth
}
```

## stitch_edge

**输入Input**：

```json
{
    "multi_restoration": "int",  // 区分多修复体和单修复体，1表示多修复体，0表示单修复体
    "out": "drc",  // 修改后的外冠 the outer shell
    "inner": "drc", // 修改后的备牙
    "cpu_info_json": { /* 之前 CPU 的输出 */ }, // Previous CPU output
    "align_edges": "int", //是否进行备牙边缘pruning、胶水缝隙膨胀、内外表面边缘对齐，1表示是，0表示否  whether to enable prep margin pruning, cement gap inflation, and outer margin adaptation. 1 for yes, 0 for no. optional, default at 1.
    "paras": {"..."},  // 前端传入的参数
}
```

# 25年7月22日更新内容
1、优化倒凹填充中的聚类算法和部分距离阈值。
2、增加备牙边缘是否处于倒凹阴影中的判断函数。（需要输入带顺序的边缘顶点索引）

# 25年6月25日更新内容
1、增加缝合冠上外冠、内冠、外冠边缘、内冠边缘顶点标识，分别用0、1、2、3表示

# 25年3月25日更新内容

1、上传新版基于TPS变形的牙冠方向倒凹填充算法。
2、filling_undercut()函数输入为备牙和倒凹方向，输出为填充后的备牙。相比于旧版本删除了备牙边缘扩展的网格这个参数。

# March 25 Update

1、Uploaded a new TPS deformation-based algorithm for directional crown undercut filling.
2、The filling_undercut() function now takes the ‌prepared tooth‌ and ‌undercut direction‌ as inputs, and outputs the ‌filled prepared tooth‌. Compared to the previous version, the parameter for the ‌edge-expanded mesh of the prepared tooth‌ has been removed.

# 9月25日更新内容

1、上线新版咬合调整算法  
2、stdcrown中保存中间模型standard_backup  
3、~~occlusion部分增加咬合区域判断，变化区域只会显示咬合区域中的部分~~  
4、更新关键点保存结构  

# Sept 25 Update

1、New occlusal adaptation algorithm (Bone anatomy) for the OG library. The other 5 libraries will be supported soon.  
2、Now stdcrown() outputs the lib tooth before any non-rigid trnaformations as "standard_backup".  
3、~~Now occlusion() ignores any non-occlusal regions to be displayed as blue when vialating the minimal thickness.~~  
4、Updated data structure for pre-defined key points of tooth libraries.  
5、Re-triangulation of the OG library to avoid mesh issues after adaptation.  

# 8月30日更新内容

1、增加多套标准牙体库，在stdcrown和postprocess中新增template_name表示不同标准牙体库，默认为"st_tooth"，可选["st_tooth","Cyber Standard v1","Generic Standard v1","Mature v1","Soft Standard v1", "Youth v1",]  
2、postprocess中paras新增参数adjust_crown，adjust_crown默认值为1，若输入为0，则不做邻接、咬合、厚度调整。  
3、postprocess和occlusion的输出中，传递cpu中间信息的参数名改为cpu_info_json，occlusion的输入需要读对应的cpu_info_json，即如果之前没有调用过occlusion，则读取postprocess中的cpu_info_json，否则读取最近一次occlusion运行结果中的cpu_info_json  
4、更新打印信息，其中points和normals为根据变换矩阵变换后的点的坐标及法线信息，axis替换为matrix，表示根据坐标轴得到的变换矩阵  
5、occlusion输出中新增fixed_points_info和fixed_cpu_info_json，分别表示如果选择厚度调整后的牙冠对应的打印信息和cpu中间信息，如果用户选择厚度调整后的牙冠，需要用fixed_points_info和fixed_cpu_info_json替换points_info和cpu_info_json  
6、occlusion新增trans_matrix输入，表示用户手动调整牙冠后对应的变换矩阵，输入中的out为已经经过变换矩阵后的外冠模型  
7、postprocess新增crown_rot_matirx输入，表示用户调整标准牙冠初始位置后的变换矩阵  
8、stitch_edge新增mesh_jaw输入  

# 8月13日更新内容  

1、occlusion() 增加一个输入align_edges，用于控制是否运行trans_neck()，默认调用trans_neck()。
2、stitch_edge() 增加一个输入align_edges，用于调用pruning备牙、dialation备牙、以及trans_neck()，默认调用以上功能。
3、接入新版pylfda中的stitch算法，调用pylfda.fill_hole和pylfda.stitch之前对备牙和牙冠进行修复。

# Aug 13 update  

1、occlusion() now has a new flag called "align_edges", to control whether to enable outer margin adaptation, which is enabled by default if this flag is not passed to occlusion().  
2、stitch_edge() now has a new flag called "align_edges", to control whether to enable prep margin pruning, cement gap inflation, and outer margin adaptation, which are enabled by default if this flag is not passed to stitch_edge().  
3、Integrate the new robust stitching algorithm from pylfda. Also we are now repairing more mesh issues and defects in the prep and outer before calling pylfda.fill_hole() and pylfda.stitch().  

# 8月1日更新内容  

1、更新邻接咬合接口，如果厚度检测算法检测到需要增厚的三角形索引值，则额外返回调整后的外冠、牙冠、调整区域面片id。  
2、增加填倒凹接口undercut_filling，流程上在stdcrown接口之后，postprocess接口之前。  
3、增加选底、支撑算法需要参数，在postprocess、occlusion和stitch_edge返回中加入points_info保存关键点信息。  
4、修复有些案例中牙冠与上下颌不在同一个坐标系的bug。  
5、修改邻接咬合间距默认值。

# Aug 1st update content

1、Update the occlusion API, if the minimum thickness detection algorithm detects triangles to be inflated, the occlusion module will additionally return the adjusted outer shell, stitched crown, and the triangle indices adjusted.  
2、Add the undercut_filling API, which should be called after the stdcrown API and before the postprocess API.  
3、Add outputs to assist the RWC orientation and support algorithm in the output of postprocess, occlusion, and stitch_edge.  
4、Fix the bug that rotate only the generated crown but not the scans.  
5、Modify the default value of the proximal/occlusion contact distance.

# Docker 版本切换示例 How to switch APIs in the Dockerfile

### 修改 `Dockerfile` 最后几行 Just modify the last few lines in the Dockerfile

**stdcrown Docker**：

```Dockerfile
CMD [ "stdcrown.handler" ]
# CMD [ "postprocess.handler" ]
# CMD [ "occlusion.handler" ]
```

**undercut_filling Docker**：

```Dockerfile
CMD [ "undercut_filling.handler" ]
```

**postprocess Docker**：

```Dockerfile
# CMD [ "stdcrown.handler" ]
CMD [ "postprocess.handler" ]
# CMD [ "occlusion.handler" ]
```

**occlusion Docker**：

```Dockerfile
# CMD [ "stdcrown.handler" ]
# CMD [ "postprocess.handler" ]
CMD [ "occlusion.handler" ]
```

**stitch_edge Docker**：

```Dockerfile
# CMD [ "stdcrown.handler" ]
# CMD [ "postprocess.handler" ]
# CMD [ "occlusion.handler" ]
CMD [ "stitch_edge.handler" ]
```

**geometric_utils Docker**：

```Dockerfile
CMD [ "geometric_utils.handler" ]
```

---

# 参数说明 Parameters

## stdcrown

**输入Input**（所有输入均为 GPU 结果 These are from GPU results aka cpu_process_info）：

```json
{
    "mesh1": "drc",  // 近中邻牙 misial adjacent tooth
    "mesh2": "drc",  // 远中邻牙 distal adjacent tooth
    "mesh_beiya": "drc",  // 备牙 prep tooth
    "mesh_upper": "drc",  // 上颌牙 upper scan
    "mesh_lower": "drc",  // 下颌牙 lower scan
    "kps": "drc array",  // 关键点信息 key points 
    "all_other_crowns": "list[drc]",  // 其他牙齿的 drc 信息 all teeth except for the prep and adjacents
    "beiya_id": "str",  // 备牙牙号 tooth number of the prep
    "voxel_logits": "array",  // 生成的牙冠关键点信息 predicted occlusal key points of the crown to be designed
    "is_single": "int",  // 单邻牙标志 is the prep only has a single adjacent
    "pt1": "array",  // 近中邻牙关键点 key points of mesh1
    "pt2": "array",  // 远中邻牙关键点 key points of mesh2
    "new_transform_list": "array",  // 坐标变换矩阵 transformation matrices
    "control_pts": "array",  // 备牙边缘采样点 control points of the prep margin 

    "template_name": "str", //模板牙牙体名称，默认为“st_tooth”, 可选["st_tooth","Cyber Standard v1","Generic Standard v1","Mature v1","Soft Standard v1", "Youth v1",]
}
```

**输出Output**：

```json
{
    "cpu_std_json": "cpu_std_json",  // 后续 CPU 使用 for other cpu algos 
    "standard": "drc",  // 外冠初始状态 initially placed lib tooth
    "inner": "mesh_beiya",  // 备牙 the prep
    "cpu_input_json": "输入内容备份", // 调试使用 for debuging only
    "standard_backup": "drc", // 未进行近远中沟对齐的结果
    "cpu_std_json_backup": "cpu_std_json_backup" //standard_backup对应的cpu_std_json信息
}
```

## undercut_filling (still under development)

**输入Input**：

```json
{
    "inner": "drc",  // 备牙，由前端输入 the prep
    "AOI": "array", //插入方向
                                 //angle of insertion, will be calculated automatically if not specified
    "AOI_or_UB": "int",  // 是否进行填倒凹操作，1表示是，0表示否
                        //whether to fill the undercut, 1 for yes, 0 for no
}
```

**输出Output**：

```json
{
    "AOI": "array",  // 插入方向，若输入中指定，则返回与输入相同，否则，返回计算出的插入方向
    // angle of insertion, same as input if specified, otherwise, the automatically calculated angle of insertion
    "inner": "drc",  // 内冠模型，若输入中filled是1，则返回填倒凹后的内冠
    // this is the prep (with undercut blocked out if filled was 1 in the input)
    "cpu_input_json": "输入内容备份",   // 调试使用 for debuging only
}
```

## postprocess

**输入Input**：

```json
{
    "cpu_std_json": { /* 之前 CPU 的输出 */ }, // Previous CPU output, P.S. "cpu_undercut_json" secretly works here too
    "standard": "drc",  // 生成牙冠的初始状态，由前端输入 initially placed lib tooth
    "inner": "drc",  // 备牙，由前端输入 the prep
    "paras": {
        "adjust_crown": "int",  //可选，默认值为1。值为0表示不对牙冠做邻接、咬合、厚度调整
    },  // 其他输入参数，如邻牙间隙距离，粘结剂缝隙大小，牙冠厚度等
    "crown_rot_matirx": "array", // 初始位置摆放的旋转矩阵 rotation matrix of the initial placement of the lib tooth
    "template_name": "str", //模板牙牙体名称，默认为“st_tooth”, 可选["st_tooth","Cyber Standard v1","Generic Standard v1","Mature v1","Soft Standard v1", "Youth v1",]   
}
```

**输出Output**：

```json
{
    "cpu_info_json": {  // 后续 CPU 使用 for other cpu algos 
        "mesh_oppo": "drc",
        "linya_points": "array"
    },
    "crown": "drc",  // 生成的牙冠，传给前端 the generated crown
    "out": "drc",  // 生成的牙冠的外表面，传给前端 the outer shell of the generated crown
    "inner": "drc",  // 生成的牙冠的内表面，传给前端 the prep
    "points_info":{
                "points": "array", // 支撑算法需要的关键点位置信息 occlusal key points on the generated crown, to assist 1st party crown support
                "normals": "array", // 支撑算法需要的关键点法向信息 normal vectors of occlusal key points on the generated, to assist 1st party crown support
                "matrix":"array", //选底算法需要的变换矩阵，shape（4，4）xyz正方向分别为远中方向、牙根方向、舌侧方向 vectors to assist 1st party crown orientation
            },
    "cpu_input_json": "输入内容备份"  // 调试使用 for debuging only
}
```

## occlusion

**输入Input**：

```json
{
    "cpu_info_json": { /* 之前 CPU 的输出 */ },  // Previous CPU output
    "out": "drc",  // 生成牙冠的外冠，由前端输入 the outer shell of the generated crown
    "inner": "drc",  // 备牙，由前端输入 the prep
    "paras":{ // 其他输入参数 any other parameters
        "ad_gap": "float",  //可选，邻牙间隙距离，单位为mm，默认值为-0.03 distance between the crown and adjcent teeth, optional, default at -0.03 mm
        "occlusal_distance": "float",  //可选，咬合间隙距离，单位为mm，默认值为-0.3 distance between the crown and the opposing tooth, optional, default at -0.3 mm
        "prox_or_occlu": "int",  //可选，默认值为2。值必须为0（只做邻接调整），1（只做咬合调整)，2（都做），或3（都不做） 
        // a flag to control whether to do adaptations, optional, default at 2. Set this to 0 for only adjust adjacent teeth, 1 for only adjust occlusal distance, 2 for adjust both, 3 for do nothing
        "align_edges": "int" ,//是否进行边缘对齐，1表示是，0表示否 whether to enable outer margin adaptation, 1 for yes, 0 for no, optional, default at 1
        "thick_flag": "int" //是否进行厚度调整，1表示是，0表示否
    },
    "trans_matrix": "array" ,//用户手动调整牙冠后的旋转矩阵，形状为(4*4)
}
```

**输出Output**：

```json
{
    "crown": "drc",  // 厚度调整前的牙冠，传给前端 the stitched crown before thickness adjustment
    "out": "drc",  // 厚度调整前的外冠，传给前端 the outer shell before thickness adjustment
    "inner": "drc",  // 生成的牙冠的内表面，传给前端 the prep
    "fixed_crown":"drc",  // 厚度调整后的牙冠，调整后的顶点已由flag标记。如果厚度不需要调整，返回"" the stitched crown after thickness adjustment, the  triangle indices that was adjusted is indicated by a flag array. An empty string will be returned if no adjustment was made
    "fixed_out":"drc",  // 厚度调整后的外冠，传给前端，如果厚度不需要调整，返回"" the outer shell after thickness adjustment. An empty string will be returned if no adjustment was made 
    "points_info":{
                "points": "array", // 支撑算法需要的关键点位置信息 occlusal key points on the generated crown, to assist 1st party crown support
                "normals": "array", // 支撑算法需要的关键点法向信息 normal vectors of occlusal key points on the generated, to assist 1st party crown support
                "matrix":"array", //选底算法需要的变换矩阵，shape（4，4）xyz正方向分别为远中方向、牙根方向、舌侧方向 vectors to assist 1st party crown orientation
            },
    "fixed_points_info":{
        "points": "array", // 支撑算法需要的关键点位置信息 occlusal key points on the generated crown, to assist 1st party crown support
        "normals": "array", // 支撑算法需要的关键点法向信息 normal vectors of occlusal key points on the generated, to assist 1st party crown support
        "matrix":"array", //选底算法需要的变换矩阵，shape（4，4）xyz正方向分别为远中方向、牙根方向、舌侧方向 vectors to assist 1st party crown orientation
    },
    "cpu_info_json": ,//后续stitch_edge或occlusion使用" for stitch_edge() or occlusion()
    "fixed_cpu_info_json": ,//后续stitch_edge或occlusion使用(选择应用厚度时对应的信息) for stitch_edge() or occlusion() ,
    "cpu_input_json": "输入内容备份"  // 调试使用 for debugging only
}
```

## stitch_edge

**输入Input**：

```json
{
    "out": "drc",  // 修改后的外冠 the outer shell
    "inner": "drc", // 修改后的备牙
    "cpu_info_json": { /* 之前 CPU 的输出 */ }, // Previous CPU output
    "align_edges": "int", //是否进行备牙边缘pruning、胶水缝隙膨胀、内外表面边缘对齐，1表示是，0表示否  whether to enable prep margin pruning, cement gap inflation, and outer margin adaptation. 1 for yes, 0 for no. optional, default at 1.
    "mesh_jaw": "drc", // 备牙附近的口扫信息，用于做备牙边缘平滑
}
``
**输出Output**：
```json
{
    "crown": "drc",  // 缝合后的牙冠 the stitched crown
    "inner": "drc", // 修改后的备牙
    // "points_info":{
    //             "points": "array", // 支撑算法需要的关键点位置信息 occlusal key points on the generated crown, to assist 1st party crown support
    //             "normals": "array", // 支撑算法需要的关键点法向信息 normal vectors of occlusal key points on the generated, to assist 1st party crown support
    //             "axis":"array", //选底算法需要的轴向信息 ，shape（2，3）咬合方向、远中指向近中方向 vectors to assist 1st party crown orientation
    //         },
    "cpu_input_json": "输入内容备份"  // 调试使用 for debugging only
}
```

## geometric_utils

**输入Input**：

```json
{
    "util_name": "transform",  // 想要调用的几何操作名称，目前只支持变换操作 the utility method name, only support "transform" for now
    "trans_mat": [[...],[...],[...],[...]], // 4x4变换矩阵 4x4 transformation matrix
    "mesh": "drc", // 输入模型 input mesh 
}
``
**输出Output**：
```json
{
    "input": "drc",  "输入内容备份"  // 调试使用   for debugging only
    "output": "drc", // 变换之后的mesh    the transformed mesh
    "State": "...", // 状态信息，包括错误信息，成功信息，警告信息 state information, including error information, success information, warning information
}
```

# 测试文件说明 Sample input/output Json files for each API

## stdcrown

**输入Input**：  
/crown_cpu/test_data/0617/gpu_result.json

**输出Output**：  
/crown_cpu/test_data/0617/std.json

## undercut_filling  

**输入Input**：  
/crown_cpu/test_data/0617/std.json

**输出Output**：  
/crown_cpu/test_data/0617/undercut_filling.json  

## postprocess  

**输入Input**：  
/crown_cpu/test_data/0617/std.json
**or** /crown_cpu/test_data/0617/undercut_filling.json  

**输出Output**：
/crown_cpu/test_data/0617/post.json  

## occlusion

**输入Input**：  
/crown_cpu/test_data/0617/post.json  

**输出Output**：  
/crown_cpu/test_data/0617/occlu.json  

## stitch_edge

**输入Input**：
/crown_cpu/test_data/0617/occlu.json  

**输出Output**：
/crown_cpu/test_data/0617/stitch_edge.json  

## geometric_utils

**输入Input**：
/crown_cpu/test_data/0617/geometric_utils_input.json  

**输出Output**：
/crown_cpu/test_data/0617/geometric_utils_output.json  
