import yaml
from faker import Faker
import random
from openai import OpenAI
from datetime import datetime, timedelta

class FinanceDataGenerator:

    def _generate_date_series(self):
        """生成有序日期序列（标准库实现）"""
        date_config = self.config['tables']['业务数据表']['columns']['数据日期']
        date_type = date_config.get('date_type', 'daily')
        fmt = date_config.get('format', '%Y%m%d')

        current = datetime.strptime(date_config['start'], fmt)
        end = datetime.strptime(date_config['end'], fmt)
        series = []

        while current <= end:
            if date_type == 'monthly':
                # 计算当月最后一天
                last_day = self._get_month_last_day(current)
                if last_day > end:  # 超过结束日期时终止
                    break
                series.append(last_day.strftime(fmt))
                current = last_day + timedelta(days=1)
            else:
                series.append(current.strftime(fmt))
                current += timedelta(days=1)
        return series

    def _get_month_last_day(self, dt):
        """获取当月最后一天（无需dateutil）"""
        # 获取下个月第一天
        if dt.month == 12:
            next_month = dt.replace(year=dt.year + 1, month=1, day=1)
        else:
            next_month = dt.replace(month=dt.month + 1, day=1)
        # 前一天即为当月最后一天
        return next_month - timedelta(days=1)



    def __init__(self, config_path, api_key):
        with open(config_path, encoding='utf-8') as f:
            self.config = yaml.safe_load(f)
        self.fake = Faker('zh_CN')
        self.client = OpenAI(api_key=api_key, base_url="https://api.deepseek.com")
        self.date_series = self._generate_date_series()
        self.date_ptr = 0  # 日期序列指针

    def _translate_sql_llm(self, table_config):
        """调用大模型生成英文字段名和注释"""

        prompt = f"""将以下中文数据库字段转换为英文命名（返回内容只可以包括一个SQL语句），并生成注释：
        列信息为：{table_config}
        请解析列信息并生成一个MySQL的建表语句，要求字段生成的时候帮我生成为英文"""

        response = self.client.chat.completions.create(
            model="deepseek-chat",
            messages=[
                {"role": "system", "content": "你是一个专业的翻译助手可以将中文翻译为数据库字段"},
                {"role": "user", "content": prompt}
            ],
            stream=False,
            temperature=0.3
        )

        # 解析模型返回结果

        raw_output = response.choices[0].message.content

        return raw_output


    def generate_date(self):
        """获取下一个有序日期"""
        if self.date_ptr >= len(self.date_series):
            raise IndexError("日期序列耗尽")


        date_str = self.date_series[self.date_ptr]
        self.date_ptr += 1
        return date_str

    def build_ddl(self):
        """生成英文字段的建表语句"""
        columns = []
        table_config = self.config['tables']['业务数据表']['columns']
        resSQL = self._translate_sql_llm(table_config)
        return resSQL

    def build_dml(self):
        """生成插入数据"""
        inserts = []
        table_config = self.config['tables']['业务数据表']['columns']
        records = self.config['tables']['业务数据表']['records']

        records =  len(self.date_series)

        for _ in range(records):
            row = []
            for col_name, config in table_config.items():
                generator = config.get('generator')
                col_type = config['type']

                # 处理不同生成器类型
                if generator == 'date_series':
                    val = self.generate_date()
                elif generator == 'enum':
                    val = random.choice(config['values'])
                elif generator == 'number_range':
                    # 根据字段类型决定生成整数还是小数
                    if 'INT' in col_type:  # 处理整数类型
                        val = random.randint(int(config['min']), int(config['max']))
                    else:  # 处理DECIMAL/FLOAT类型
                        val = round(random.uniform(config['min'], config['max']), 2)

                elif generator == 'decimal_percent':
                    min_val = config.get('min', 0.0)
                    max_val = config.get('max', 1.0)
                    val = round(random.uniform(min_val, max_val), 2)

                else:
                    val = "NULL"

                # 类型安全格式化
                if isinstance(val, (int, float)):
                    if 'DECIMAL' in config['type']:
                        val = f"{val:.2f}"
                    else:
                        val = str(val)
                elif isinstance(val, str) and val != "NULL":
                    val = f"'{val}'"

                row.append(val)

            inserts.append(f"INSERT INTO `业务数据表` VALUES ({', '.join(row)});")

        return '\n'.join(inserts)

    def export_sql(self):
        # with open('create.sql', 'w', encoding='utf-8') as f:
        #     f.write(self.build_ddl())
        with open('insert.sql', 'w', encoding='utf-8') as f:
            f.write(self.build_dml())


if __name__ == "__main__":
    # 使用示例
    generator = FinanceDataGenerator("config.yaml", "sk-76238f9297f24fe8889bcfefb3642931")
    generator.export_sql()
