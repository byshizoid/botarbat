import discord
from discord.ext import commands
from discord import app_commands
import os
import sys
from datetime import datetime, timedelta
import json
import re
from typing import Optional
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

# Настройка для Windows
if sys.platform == 'win32':
    try:
        import winloop
        winloop.install()
    except ImportError:
        import asyncio
        if sys.version_info >= (3, 8):
            asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

# Настройка intents
intents = discord.Intents.default()
try:
    intents.message_content = True
except AttributeError:
    pass
try:
    intents.members = True
except AttributeError:
    pass

# Создание бота
bot = commands.Bot(command_prefix='!', intents=intents)

# Файл для хранения запросов отгула
OTGUL_FILE = 'otgul_requests.json'

def load_requests():
    """Загружает запросы отгула из файла"""
    if os.path.exists(OTGUL_FILE):
        with open(OTGUL_FILE, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_requests(requests):
    """Сохраняет запросы отгула в файл"""
    with open(OTGUL_FILE, 'w', encoding='utf-8') as f:
        json.dump(requests, f, ensure_ascii=False, indent=2)

def add_request(user_id, username, date, time=None, duration=None, static=None, department=None, reason=None):
    """Добавляет новый запрос отгула"""
    requests = load_requests()
    max_id = max([r['id'] for r in requests], default=0)
    request = {
        'id': max_id + 1,
        'user_id': user_id,
        'username': username,
        'date': date,
        'time': time,
        'duration': duration,
        'static': static,
        'department': department or 'ГИБДД',
        'reason': reason,
        'status': 'pending',
        'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    }
    requests.append(request)
    save_requests(requests)
    return request

def get_request_by_id(request_id):
    """Получает запрос по ID"""
    requests = load_requests()
    return next((r for r in requests if r['id'] == request_id), None)

def update_request_status(request_id, status, moderator_id=None, moderator_name=None, rejection_reason=None):
    """Обновляет статус запроса"""
    requests = load_requests()
    request = next((r for r in requests if r['id'] == request_id), None)
    if request:
        request['status'] = status
        if moderator_id:
            request['moderator_id'] = moderator_id
        if moderator_name:
            request['moderator_name'] = moderator_name
        if rejection_reason:
            request['rejection_reason'] = rejection_reason
        if status != 'pending':
            request['processed_at'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        save_requests(requests)
    return request

def has_today_request(user_id):
    """Проверяет, есть ли у пользователя заявка на сегодня"""
    requests = load_requests()
    today = datetime.now().strftime('%d.%m.%Y')
    user_requests = [r for r in requests if r['user_id'] == str(user_id) and r['date'] == today and r['status'] == 'pending']
    return len(user_requests) > 0

def parse_time_duration(time_str):
    """Парсит время и вычисляет продолжительность"""
    match = re.match(r'(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})', time_str)
    if match:
        start_h, start_m = int(match.group(1)), int(match.group(2))
        end_h, end_m = int(match.group(3)), int(match.group(4))
        
        start = timedelta(hours=start_h, minutes=start_m)
        end = timedelta(hours=end_h, minutes=end_m)
        duration = end - start
        
        if duration.total_seconds() <= 0:
            return None, None, "Время окончания должно быть позже времени начала"
        
        hours = int(duration.total_seconds() // 3600)
        minutes = int((duration.total_seconds() % 3600) // 60)
        
        if hours > 1 or (hours == 1 and minutes > 0):
            return None, None, "Максимальная длительность отгула: 1 час"
        
        duration_str = f"{hours} ч" if hours > 0 else f"{minutes} мин"
        return time_str, duration_str, None
    
    return None, None, "Неверный формат времени. Используйте: ЧЧ:ММ - ЧЧ:ММ"

def is_future_time(time_str):
    """Проверяет, что время в будущем"""
    match = re.match(r'(\d{1,2}):(\d{2})\s*-\s*(\d{1,2}):(\d{2})', time_str)
    if match:
        now = datetime.now()
        start_h, start_m = int(match.group(1)), int(match.group(2))
        request_time = now.replace(hour=start_h, minute=start_m, second=0, microsecond=0)
        
        if request_time < now:
            request_time += timedelta(days=1)
        
        return request_time > now
    return False

def can_moderate(user):
    """Проверяет, может ли пользователь одобрять/отклонять заявки"""
    # Проверка по правам (управление сообщениями)
    if user.guild_permissions.manage_messages:
        return True
    
    # Проверка по ролям (можно настроить список ролей)
    if user.guild:
        moderator_roles = [
            "Начальник УГИБДД",
            "Зам. Нач. УГИБДД",
            "Начальник ЦППС",
            "Зам. Начальника ЦППС",
            "Модератор",
            "Администратор"
        ]
        user_roles = [role.name for role in user.roles]
        for mod_role in moderator_roles:
            if mod_role in user_roles:
                return True
    
    return False

@bot.event
async def on_ready():
    print(f'{bot.user} подключен к Discord!')
    print('Синхронизация команд с Discord...')
    try:
        synced = await bot.tree.sync()
        print(f'✅ Синхронизировано {len(synced)} команд:')
        for cmd in synced:
            print(f'   - /{cmd.name}')
    except Exception as e:
        print(f'❌ Ошибка синхронизации команд: {e}')
    
    requests = load_requests()
    pending_count = len([r for r in requests if r['status'] == 'pending'])
    if pending_count > 0:
        print(f'Восстановление {pending_count} активных заявок...')
        for req in requests:
            if req['status'] == 'pending':
                view = OtgulButtonsView(req['id'])
                bot.add_view(view)
        print('✅ Активные заявки восстановлены')
    
    print('🚀 Бот готов к работе!')

@bot.tree.command(name='инфо_отгулы', description='Показать информацию о системе отгулов (для модераторов)')
async def info_otguls(interaction: discord.Interaction):
    """Показать информационное сообщение о системе отгулов"""
    if not can_moderate(interaction.user):
        await interaction.response.send_message('❌ У вас нет прав для использования этой команды', ephemeral=True)
        return
    
    embed = discord.Embed(
        title='🧳 Система подачи заявок на отгулы',
        description='Здесь вы можете подать заявку на отгул в рабочее время.',
        color=discord.Color.blue(),
        timestamp=datetime.now()
    )
    
    embed.add_field(
        name='⚠️ Важные ограничения:',
        value=(
            '• Максимальная длительность отгула: **1 час**\n'
            '• Можно подать только на **сегодняшний день**\n'
            '• Отгул разрешен только в **рабочее время**\n'
            '• Можно подать только **одну заявку в день**\n'
            '• Время должно быть в **будущем** относительно текущего момента'
        ),
        inline=False
    )
    
    embed.add_field(
        name='📝 Что нужно указать:',
        value=(
            '• Имя и фамилия\n'
            '• Статик (123-456)\n'
            '• Время начала и конца отгула (формат НН:ММ)\n'
            '• Причина взятия отгула'
        ),
        inline=False
    )
    
    embed.add_field(
        name='🔍 Рассмотрение заявок:',
        value=(
            '• Заявки рассматривают командиры вашего подразделения\n'
            '• Уведомление о результате придет в **личные сообщения**\n'
            '• Вы можете **удалить** свою заявку до рассмотрения\n'
            '• При отклонении можно подать новую заявку в тот же день'
        ),
        inline=False
    )
    
    current_time = datetime.now().strftime('%d.%m.%Y %H:%M')
    embed.set_footer(text=f'Нажмите кнопку ниже, чтобы подать заявку • {current_time}')
    
    class SubmitButton(discord.ui.Button):
        def __init__(self):
            super().__init__(label='Подать заявку на отгул', style=discord.ButtonStyle.success, emoji='✈️')
        
        async def callback(self, interaction: discord.Interaction):
            modal = OtgulModal()
            await interaction.response.send_modal(modal)
    
    submit_button = SubmitButton()
    
    view = discord.ui.View()
    view.add_item(submit_button)
    
    await interaction.response.send_message(embed=embed, view=view)

@bot.tree.command(name='отгул', description='Запросить отгул (через модальное окно)')
async def otgul_modal_command(interaction: discord.Interaction):
    """Команда для открытия модального окна заявки на отгул"""
    modal = OtgulModal()
    await interaction.response.send_modal(modal)

# Модальное окно для подачи заявки
class OtgulModal(discord.ui.Modal, title='🧳 Заявка на отгул'):
    имя_фамилия = discord.ui.TextInput(
        label='Имя и фамилия',
        placeholder='Иван Иванов',
        required=True,
        max_length=50
    )
    
    статик = discord.ui.TextInput(
        label='Статик',
        placeholder='123-456',
        required=True,
        max_length=20
    )
    
    время = discord.ui.TextInput(
        label='Время (ЧЧ:ММ - ЧЧ:ММ)',
        placeholder='15:00 - 16:00',
        required=True,
        max_length=20
    )
    
    причина = discord.ui.TextInput(
        label='Причина',
        placeholder='Гражданские дела',
        required=True,
        style=discord.TextStyle.paragraph,
        max_length=200
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        username = user.display_name or user.name
        
        today = datetime.now().strftime('%d.%m.%Y')
        
        if has_today_request(user.id):
            await interaction.response.send_message(
                '❌ У вас уже есть активная заявка на сегодня! Можно подать только одну заявку в день.',
                ephemeral=True
            )
            return
        
        time_str, duration_str, error = parse_time_duration(self.время.value)
        if error:
            await interaction.response.send_message(f'❌ {error}', ephemeral=True)
            return
        
        if not is_future_time(self.время.value):
            await interaction.response.send_message(
                '❌ Время должно быть в будущем относительно текущего момента!',
                ephemeral=True
            )
            return
        
        request = add_request(
            str(user.id),
            self.имя_фамилия.value,
            today,
            time=time_str,
            duration=duration_str,
            static=self.статик.value,
            reason=self.причина.value
        )
        
        embed = discord.Embed(
            title='🧳 Заявка на отгул',
            color=discord.Color.blue(),
            timestamp=datetime.now()
        )
        
        embed.add_field(
            name='👤 Заявитель',
            value=f"{user.mention} ({self.имя_фамилия.value})",
            inline=False
        )
        
        embed.add_field(name='🏷️ Статик', value=self.статик.value, inline=True)
        embed.add_field(name='📅 Дата', value=today, inline=True)
        embed.add_field(name='⏰ Время', value=f"{time_str} ({duration_str})", inline=True)
        embed.add_field(name='✏️ Причина', value=self.причина.value, inline=False)
        embed.add_field(name='🏛️ Подразделение', value='ГИБДД', inline=False)
        embed.add_field(name='📢 Статус:', value='⏳ Ожидает рассмотрения', inline=False)
        
        embed.set_footer(text=f'ID запроса: #{request["id"]}')
        
        view = OtgulButtonsView(request["id"])
        
        mentions = ""
        if interaction.guild:
            role_names = [
                "Начальник УГИБДД",
                "Зам. Нач. УГИБДД",
                "Начальник ЦППС",
                "Зам. Начальника ЦППС"
            ]
            for role_name in role_names:
                role = discord.utils.get(interaction.guild.roles, name=role_name)
                if role:
                    mentions += f"{role.mention} "
        
        await interaction.response.send_message(
            content=mentions if mentions else None,
            embed=embed,
            view=view
        )

# View с кнопками для заявки
class OtgulButtonsView(discord.ui.View):
    def __init__(self, request_id):
        super().__init__(timeout=None)
        self.request_id = request_id
        
        class ApproveButton(discord.ui.Button):
            def __init__(self, view_instance, request_id):
                super().__init__(
                    label='Одобрить', 
                    style=discord.ButtonStyle.success, 
                    emoji='✅',
                    custom_id=f'approve_{request_id}'
                )
                self.view_instance = view_instance
            
            async def callback(self, interaction: discord.Interaction):
                await self.view_instance.handle_approve(interaction)
        
        class RejectButton(discord.ui.Button):
            def __init__(self, view_instance, request_id):
                super().__init__(
                    label='Отклонить', 
                    style=discord.ButtonStyle.danger, 
                    emoji='❌',
                    custom_id=f'reject_{request_id}'
                )
                self.view_instance = view_instance
            
            async def callback(self, interaction: discord.Interaction):
                await self.view_instance.handle_reject(interaction)
        
        class DeleteButton(discord.ui.Button):
            def __init__(self, view_instance, request_id):
                super().__init__(
                    label='Удалить', 
                    style=discord.ButtonStyle.secondary, 
                    emoji='🗑️',
                    custom_id=f'delete_{request_id}'
                )
                self.view_instance = view_instance
            
            async def callback(self, interaction: discord.Interaction):
                await self.view_instance.handle_delete(interaction)
        
        self.add_item(ApproveButton(self, request_id))
        self.add_item(RejectButton(self, request_id))
        self.add_item(DeleteButton(self, request_id))
    
    async def handle_approve(self, interaction: discord.Interaction):
        if not can_moderate(interaction.user):
            await interaction.response.send_message(
                '❌ У вас нет прав для одобрения заявок.\n'
                'Требуется право "Управление сообщениями" или одна из ролей модератора.',
                ephemeral=True
            )
            return
        
        request = get_request_by_id(self.request_id)
        if not request:
            await interaction.response.send_message('❌ Заявка не найдена', ephemeral=True)
            return
        
        if request['status'] != 'pending':
            await interaction.response.send_message('❌ Эта заявка уже обработана', ephemeral=True)
            return
        
        # Получаем имя модератора
        moderator = interaction.user
        moderator_name = moderator.display_name or moderator.name
        
        # Обновляем статус с информацией о модераторе
        update_request_status(
            self.request_id, 
            'approved', 
            str(moderator.id),
            moderator_name
        )
        
        # Обновляем embed
        embed = interaction.message.embeds[0]
        embed.set_field_at(-1, name='📢 Статус:', value=f'✅ Одобрено\n👤 Одобрил: {moderator_name}', inline=False)
        embed.color = discord.Color.green()
        
        # Отключаем кнопки
        for item in self.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=self)
        
        # Уведомляем пользователя
        try:
            user = await bot.fetch_user(int(request['user_id']))
            await user.send(f'✅ Ваш запрос на отгул #{self.request_id} был одобрен модератором {moderator_name}!')
        except:
            pass
    
    async def handle_reject(self, interaction: discord.Interaction):
        if not can_moderate(interaction.user):
            await interaction.response.send_message(
                '❌ У вас нет прав для отклонения заявок.\n'
                'Требуется право "Управление сообщениями" или одна из ролей модератора.',
                ephemeral=True
            )
            return
        
        request = get_request_by_id(self.request_id)
        if not request:
            await interaction.response.send_message('❌ Заявка не найдена', ephemeral=True)
            return
        
        if request['status'] != 'pending':
            await interaction.response.send_message('❌ Эта заявка уже обработана', ephemeral=True)
            return
        
        modal = RejectModal(self.request_id)
        await interaction.response.send_modal(modal)
    
    async def handle_delete(self, interaction: discord.Interaction):
        request = get_request_by_id(self.request_id)
        if not request:
            await interaction.response.send_message('❌ Заявка не найдена', ephemeral=True)
            return
        
        if str(interaction.user.id) != request['user_id'] and not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message('❌ Вы можете удалить только свою заявку', ephemeral=True)
            return
        
        if request['status'] != 'pending':
            await interaction.response.send_message('❌ Можно удалить только заявки, ожидающие рассмотрения', ephemeral=True)
            return
        
        requests = load_requests()
        requests = [r for r in requests if r['id'] != self.request_id]
        save_requests(requests)
        
        await interaction.response.send_message('✅ Заявка удалена', ephemeral=True)
        await interaction.message.delete()

# Модальное окно для причины отклонения
class RejectModal(discord.ui.Modal, title='❌ Отклонение заявки'):
    def __init__(self, request_id):
        super().__init__()
        self.request_id = request_id
    
    причина = discord.ui.TextInput(
        label='Причина отклонения',
        placeholder='Укажите причину отклонения',
        required=False,
        style=discord.TextStyle.paragraph,
        max_length=200
    )
    
    async def on_submit(self, interaction: discord.Interaction):
        request = get_request_by_id(self.request_id)
        if not request:
            await interaction.response.send_message('❌ Заявка не найдена', ephemeral=True)
            return
        
        # Получаем имя модератора
        moderator = interaction.user
        moderator_name = moderator.display_name or moderator.name
        
        update_request_status(
            self.request_id, 
            'rejected', 
            str(moderator.id),
            moderator_name,
            self.причина.value or None
        )
        
        # Обновляем embed
        embed = interaction.message.embeds[0]
        embed.set_field_at(-1, name='📢 Статус:', value=f'❌ Отклонено\n👤 Отклонил: {moderator_name}', inline=False)
        embed.color = discord.Color.red()
        if self.причина.value:
            embed.add_field(name='Причина отклонения', value=self.причина.value, inline=False)
        
        # Отключаем кнопки
        view = OtgulButtonsView(self.request_id)
        for item in view.children:
            item.disabled = True
        
        await interaction.response.edit_message(embed=embed, view=view)
        
        # Уведомляем пользователя
        try:
            user = await bot.fetch_user(int(request['user_id']))
            message = f'❌ Ваш запрос на отгул #{self.request_id} был отклонен модератором {moderator_name}.'
            if self.причина.value:
                message += f'\nПричина: {self.причина.value}'
            await user.send(message)
        except:
            pass

@bot.tree.command(name='мои_отгулы', description='Показать мои запросы на отгул')
async def my_otguls(interaction: discord.Interaction):
    """Показать все запросы отгула пользователя"""
    user_id = str(interaction.user.id)
    requests = load_requests()
    user_requests = [r for r in requests if r['user_id'] == user_id]
    
    if not user_requests:
        await interaction.response.send_message('❌ У вас нет запросов на отгул', ephemeral=True)
        return
    
    embed = discord.Embed(
        title=f'📋 Ваши запросы на отгул ({len(user_requests)})',
        color=discord.Color.green()
    )
    
    for req in user_requests[-10:]:
        status_emoji = '✅' if req['status'] == 'approved' else '❌' if req['status'] == 'rejected' else '⏳'
        status_text = {
            'pending': 'Ожидает',
            'approved': 'Одобрен',
            'rejected': 'Отклонен'
        }.get(req['status'], req['status'])
        
        info = f'Статус: {status_text}'
        if req['status'] == 'approved' and req.get('moderator_name'):
            info += f'\nОдобрил: {req["moderator_name"]}'
        elif req['status'] == 'rejected' and req.get('moderator_name'):
            info += f'\nОтклонил: {req["moderator_name"]}'
        
        embed.add_field(
            name=f'{status_emoji} Запрос #{req["id"]} - {req["date"]}',
            value=info,
            inline=False
        )
    
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Запуск бота
if __name__ == '__main__':
    token = os.getenv('DISCORD_TOKEN')
    
    if not token:
        print('❌ Ошибка: DISCORD_TOKEN не установлен!')
        print('📝 Создайте файл .env и добавьте туда DISCORD_TOKEN=ваш_токен')
        sys.exit(1)
    
    if 'ваш_токен' in token.lower() or token.strip() == '' or len(token) < 20:
        print('❌ Ошибка: Токен не установлен или неверный!')
        print('📝 Откройте файл .env и замените "ваш_токен_здесь" на реальный токен от Discord')
        print('🔗 Получить токен: https://discord.com/developers/applications')
        sys.exit(1)
    
    print('🚀 Запуск бота...')
    try:
        bot.run(token)
    except discord.errors.LoginFailure:
        print('❌ Ошибка авторизации: Неверный токен!')
        print('📝 Проверьте, что токен в файле .env правильный')
        sys.exit(1)
    except discord.errors.PrivilegedIntentsRequired as e:
        print('❌ Ошибка: Не включены привилегированные интенты!')
        print('📝 Включите MESSAGE CONTENT INTENT в Discord Developer Portal')
        sys.exit(1)

