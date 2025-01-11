import os
import json
import shutil

def standardize_model(model_dir):
    """
    标准化Live2D模型文件结构
    :param model_dir: 模型文件夹路径
    """
    # 创建expressions和motions文件夹
    expressions_dir = os.path.join(model_dir, "expressions")
    motions_dir = os.path.join(model_dir, "motions")
    os.makedirs(expressions_dir, exist_ok=True)
    os.makedirs(motions_dir, exist_ok=True)

    # 查找model3.json文件
    model_json_files = [f for f in os.listdir(model_dir) if f.endswith('.model3.json')]
    if not model_json_files:
        print(f"在 {model_dir} 中未找到model3.json文件")
        return
    
    model_json_path = os.path.join(model_dir, model_json_files[0])
    
    # 读取现有的model3.json
    with open(model_json_path, 'r', encoding='utf-8') as f:
        model_data = json.load(f)
    
    # 初始化FileReferences如果不存在
    if 'FileReferences' not in model_data:
        model_data['FileReferences'] = {}

    # 处理表情文件
    expressions = []
    for root, _, files in os.walk(model_dir):
        for file in files:
            if file.endswith('.exp3.json'):
                # 跳过已经在expressions文件夹中的文件
                if 'expressions' in root:
                    continue
                
                # 移动文件到expressions文件夹
                src_path = os.path.join(root, file)
                dst_path = os.path.join(expressions_dir, file)
                if not os.path.exists(dst_path):
                    shutil.copy2(src_path, dst_path)
                
                # 添加到expressions列表
                name = os.path.splitext(file)[0]
                expressions.append({
                    "Name": name,
                    "File": f"expressions/{file}"
                })
    
    # 处理动作文件
    motions = {}
    motion_files = []
    for root, _, files in os.walk(model_dir):
        for file in files:
            if file.endswith('.motion3.json'):
                # 跳过已经在motions文件夹中的文件
                if 'motions' in root:
                    continue
                
                # 移动文件到motions文件夹
                src_path = os.path.join(root, file)
                dst_path = os.path.join(motions_dir, file)
                if not os.path.exists(dst_path):
                    shutil.copy2(src_path, dst_path)
                motion_files.append(file)

    # 根据文件名智能分组
    for file in motion_files:
        # 移除.motion3.json后缀
        base_name = file.replace('.motion3.json', '')
        
        # 处理特殊分组标记 "@"
        if '@' in base_name:
            group_name, target = base_name.split('@')
            # 如果前面还有下划线，取下划线前的部分
            if '_' in group_name:
                group_name = group_name.split('_')[0]
            group_name = f"{group_name}@{target}"
        else:
            # 没有@标记的情况
            # 尝试按下划线分割并获取第一部分作为组名
            parts = base_name.split('_')
            if len(parts) > 1:
                # 如果文件名中有数字（如main_01），使用前缀作为组名
                group_name = parts[0]
            else:
                # 如果没有下划线，整个名称作为组名
                group_name = base_name

        # 确保组名首字母大写
        group_name = group_name.capitalize()
        
        # 初始化分组
        if group_name not in motions:
            motions[group_name] = []
        
        # 添加到对应分组
        motions[group_name].append({
            "File": f"motions/{file}",
            "FadeInTime": 0.5,
            "FadeOutTime": 0.5
        })
    
    # 更新model3.json
    if expressions:
        model_data['FileReferences']['Expressions'] = expressions
    if motions:
        model_data['FileReferences']['Motions'] = motions
    
    # 保存更新后的model3.json
    with open(model_json_path, 'w', encoding='utf-8') as f:
        json.dump(model_data, f, indent=4, ensure_ascii=False)

    print(f"已完成 {model_dir} 的标准化")
