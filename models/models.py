# -*- coding: utf-8 -*-
import time

from odoo import models, fields, api, exceptions
import datetime

WORKFLOW_STATE_SELECTION = [
    ('draft', '草稿'),
    ('confirm', '待审批'),
    ('reject', '审批不通过'),
    ('complete', '审批通过')
]


# 1.员工可填写请假表单，包括请假人、部门、开始时间、结束时间、天数、类型（病假、事假、年假），请假原因。
class Leave(models.Model):
    _name = 'leave.leave'
    _description = '请假表单'

    name = fields.Many2one('res.users', string='姓名', default=lambda self: self.env.user, readonly=True)
    department = fields.Char('部门', default=lambda self: self.env.user.department.name, readonly=True)
    start_time = fields.Date(string='开始时间', states={'draft': [('readonly', False)]}, readonly=True, required=True)
    start_am_pm = fields.Selection([('am', '上午'), ('pm', '下午')], string='开始时间上/下午',
                                   states={'draft': [('readonly', False)]},
                                   readonly=True, required=True)
    stop_time = fields.Date(string='结束时间', states={'draft': [('readonly', False)]}, readonly=True, required=True)
    stop_am_pm = fields.Selection([('am', '上午'), ('pm', '下午')], string='结束时间上/下午',
                                  states={'draft': [('readonly', False)]},
                                  readonly=True, required=True)
    rest = fields.Float('可调休天数', digits=(2, 1), default=lambda self: self.env.user.user_rest, readonly=True)
    year_rest = fields.Float('年假', digits=(2, 1), default=lambda self: self.env.user.user_year_rest, readonly=True)
    leave_day = fields.Float('请假天数', digits=(2, 1), readonly=True)
    leave_type = fields.Selection([('ill', '病假'), ('thing', '事假'), ('year', '年假'), ('day_off', '调休')], string='请假类型',
                                  states={'draft': [('readonly', False)]}, readonly=True, required=True)
    leave_reason = fields.Char('请假原因', states={'draft': [('readonly', False)]}, readonly=True)
    count_name = fields.Integer('请假人数', default=1)
    state = fields.Selection(WORKFLOW_STATE_SELECTION, default='draft', string='状态', readonly=True, copy=False,
                             track_visibility='onchange')
    exam_manager = fields.Many2one('leave.exam', '审批人')

    # button提交按钮
    def button_submit(self):
        start_am = self.env['leave.leave'].search([('start_am_pm', '=', 'am')])
        start_pm = self.env['leave.leave'].search([('start_am_pm', '=', 'pm')])
        stop_am = self.env['leave.leave'].search([('stop_am_pm', '=', 'am')])
        stop_pm = self.env['leave.leave'].search([('stop_am_pm', '=', 'pm')])
        # 请假天数计算
        if self.stop_time and self.start_time:
            DATETIME_FORMAT = "%Y-%m-%d"
            from_dt = datetime.datetime.strptime(str(self.start_time), DATETIME_FORMAT)
            to_dt = datetime.datetime.strptime(str(self.stop_time), DATETIME_FORMAT)
            result_time_str = to_dt - from_dt
            diff_day = result_time_str.days
        if (from_dt == to_dt and start_am and stop_am) or (from_dt == to_dt and start_pm and stop_pm) or (
                from_dt != to_dt and start_am and stop_am):
            self.leave_day = float(diff_day) + 0.5
        elif (from_dt == to_dt and start_am and stop_pm) or (from_dt != to_dt and start_am and stop_pm):
            self.leave_day = float(diff_day) + 1.0
        elif from_dt == to_dt and start_pm and stop_am:
            raise exceptions.ValidationError("请假结束时间不得低于开始时间")
        else:
            self.leave_day = float(diff_day)

        # 请假时间判断约束
        if self.start_time and self.start_time - fields.date.today() < datetime.timedelta(days=3):
            raise exceptions.ValidationError("请假开始时间不得低于当前日期3天")
        if self.stop_time and self.start_time > self.stop_time:
            raise exceptions.ValidationError("请假结束时间不得低于开始时间")

        for r in self:
            # 调休天数判断
            if r.leave_type == 'day_off' and self.leave_day > self.rest:
                raise exceptions.ValidationError("您的调休天数不足")
            # 年假判断约束
            elif r.leave_type == 'year' and r.leave_day > r.year_rest:
                raise exceptions.ValidationError("您的年假天数不足")

        times = self.env['leave.leave'].search([('create_uid', '=', self.env.uid)])
        stop_times = []
        start_times = []
        i = 0
        j = 0
        for ti in times:
            stop_times.append(ti.stop_time)
            start_times.append(ti.start_time)
        for r in self:
            for start in start_times:
                for stop in stop_times:
                    i += 1
                    if i >= 2:
                        break
                    if r.start_time > start and r.stop_time < stop:
                        raise exceptions.ValidationError("选择时间与请假记录时间有重复")
        for r in self:
            for start in start_times:
                if r.start_time == start or r.stop_time == stop:
                    j += 1
                    if j >= 2:
                        raise exceptions.ValidationError("选择时间与请假记录时间有重复")

        self.write({'state': 'confirm'})

    # button驳回拒绝按钮
    @api.multi
    def button_fail(self):
        # 当前状态下不可修改
        for r in self:
            # 员工权限设置
            staff_group = r.env['res.groups'].search([('full_name', 'ilike', '请假系统 / 员工')]).users
            department_manager_group = r.env['res.groups'].search([('full_name', 'ilike', '请假系统 / 部门经理')]).users
            staffs = []
            department_managers = []
            for staff in staff_group:
                staffs.append(staff.id)
            for department_manager in department_manager_group:
                department_managers.append(department_manager.id)
            if (self.env.uid in staffs) and (self.env.uid in department_managers):
                r.write({'state': 'reject'})
            else:
                raise exceptions.ValidationError("你没有权限，请联系你的管理员")
            # 审批后不可修改
            if r.state == 'draft' or r.state == 'complete' or r.state == 'reject':
                print()
            else:
                r.write({'state': 'reject'})

    # button通过按钮
    @api.multi
    def button_pass(self):
        # 当前状态下不可修改
        for r in self:
            # 员工权限设置
            staff_group = r.env['res.groups'].search([('full_name', 'ilike', '请假系统 / 员工')]).users
            department_manager_group = r.env['res.groups'].search([('full_name', 'ilike', '请假系统 / 部门经理')]).users
            staffs = []
            department_managers = []
            for staff in staff_group:
                staffs.append(staff.id)
            for department_manager in department_manager_group:
                department_managers.append(department_manager.id)
            if (self.env.uid in staffs) and (self.env.uid in department_managers):
                r.write({'state': 'complete'})
            else:
                raise exceptions.ValidationError("你没有权限，请联系你的管理员")

            # 审批状态修改限制
            if r.state == 'reject' or r.state == 'complete' or r.state == 'draft':
                print()
            elif r.leave_type == 'year':
                if self.env.user.user_year_rest > 0 and self.env.user.user_year_rest >= r.leave_day:
                    r.year_rest -= r.leave_day
                    self.env.user.user_year_rest -= r.leave_day
                    r.write({'state': 'complete'})
                else:
                    r.write({'state': 'reject'})
            elif r.leave_type == 'day_off':
                if r.env.user.user_rest > 0 and r.env.user.user_rest >= r.leave_day:
                    r.rest -= r.leave_day
                    r.env.user.user_rest -= r.leave_day
                    r.write({'state': 'complete'})
                else:
                    r.write({'state': 'reject'})
            elif r.leave_type == 'thing' or r.leave_type == 'ill':
                r.write({'state': 'complete'})


# 2.员工可填写加班表单，包括加班人、部门、开始时间、结束时间、天数、加班原因。
class Overtime(models.Model):
    _name = 'leave.overtime'
    _description = '加班表单'

    name = fields.Many2one('res.users', '姓名', required=True, default=lambda self: self.env.user, readonly=True)
    department = fields.Char('部门', default=lambda self: self.env.user.department.name, readonly=True)
    start_time = fields.Date('开始时间', states={'draft': [('readonly', False)]}, readonly=True, required=True)
    start_am_pm = fields.Selection([('am', '上午'), ('pm', '下午')], string='开始时间上/下午',
                                   states={'draft': [('readonly', False)]},
                                   readonly=True, required=True)
    stop_time = fields.Date(string='结束时间', states={'draft': [('readonly', False)]}, readonly=True, required=True)
    stop_am_pm = fields.Selection([('am', '上午'), ('pm', '下午')], string='结束时间上/下午',
                                  states={'draft': [('readonly', False)]},
                                  readonly=True, required=True)
    over_reason = fields.Char('加班原因', states={'draft': [('readonly', False)]}, readonly=True)
    over_day = fields.Float('加班天数', digits=(2, 1), readonly=True)
    state = fields.Selection(WORKFLOW_STATE_SELECTION, default='draft', string='状态', readonly=True, copy=False,
                             track_visibility='onchange')

    # button提交按钮
    def button_submit(self):
        start_am = self.env['leave.overtime'].search([('start_am_pm', '=', 'am')])
        start_pm = self.env['leave.overtime'].search([('start_am_pm', '=', 'pm')])
        stop_am = self.env['leave.overtime'].search([('stop_am_pm', '=', 'am')])
        stop_pm = self.env['leave.overtime'].search([('stop_am_pm', '=', 'pm')])
        # 加班天数计算
        if self.stop_time and self.start_time:
            DATETIME_FORMAT = "%Y-%m-%d"
            from_dt = datetime.datetime.strptime(str(self.start_time), DATETIME_FORMAT)
            to_dt = datetime.datetime.strptime(str(self.stop_time), DATETIME_FORMAT)
            result_time_str = to_dt - from_dt
            diff_day = result_time_str.days
        if (start_am and stop_am) or (from_dt == to_dt and start_pm and stop_pm):
            self.over_day = float(diff_day) + 0.5
        elif (from_dt == to_dt and start_am and stop_pm) or (from_dt != to_dt and start_am and stop_pm):
            self.over_day = float(diff_day) + 1.0
        elif from_dt == to_dt and start_pm and stop_am:
            raise exceptions.ValidationError("加班结束时间不得低于开始时间")
        else:
            self.over_day = float(diff_day)

        # 加班时间判断
        if self.stop_time and self.start_time > self.stop_time:
            raise exceptions.ValidationError("加班结束时间不得低于开始时间")

        times = self.env['leave.overtime'].search([('create_uid', '=', self.env.uid)])
        stop_times = []
        start_times = []
        i = 0
        j = 0
        for ti in times:
            stop_times.append(ti.stop_time)
            start_times.append(ti.start_time)
        for r in self:
            for start in start_times:
                for stop in stop_times:
                    i += 1
                    if i >= 2:
                        break
                    if r.start_time > start and r.stop_time < stop:
                        raise exceptions.ValidationError("选择时间与请假记录时间有重复")
        for r in self:
            for start in start_times:
                if r.start_time == start or r.stop_time == stop:
                    j += 1
                    if j >= 2:
                        raise exceptions.ValidationError("选择时间与请假记录时间有重复")
        self.write({'state': 'confirm'})

    # button驳回拒绝按钮
    @api.multi
    def button_fail(self):
        for r in self:
            # 员工权限设置
            staff_group = r.env['res.groups'].search([('full_name', 'ilike', '请假系统 / 员工')]).users
            department_manager_group = r.env['res.groups'].search([('full_name', 'ilike', '请假系统 / 部门经理')]).users
            staffs = []
            department_managers = []
            for staff in staff_group:
                staffs.append(staff.id)
            for department_manager in department_manager_group:
                department_managers.append(department_manager.id)
            if (self.env.uid in staffs) and (self.env.uid in department_managers):
                r.write({'state': 'reject'})
            else:
                raise exceptions.ValidationError("你没有权限，请联系你的管理员")
            # 当前状态下不可修改
            if r.state == 'draft' or r.state == 'complete' or r.state == 'reject':
                print()
            else:
                r.write({'state': 'reject'})

    # button通过按钮
    def button_pass(self):
        # 当前状态下不可修改
        for r in self:
            staff_group = r.env['res.groups'].search([('full_name', 'ilike', '请假系统 / 员工')]).users
            department_manager_group = r.env['res.groups'].search([('full_name', 'ilike', '请假系统 / 部门经理')]).users
            staffs = []
            department_managers = []
            for staff in staff_group:
                staffs.append(staff.id)
            for department_manager in department_manager_group:
                department_managers.append(department_manager.id)
            if (self.env.uid in staffs) and (self.env.uid in department_managers):
                r.write({'state': 'complete'})
            else:
                raise exceptions.ValidationError("你没有权限，请联系你的管理员")
            # 员工权限设置
            if r.state == 'draft' or r.state == 'reject' or r.state == 'complete':
                print()
            elif r.over_day:
                r.env.user.user_rest += r.over_day
                r.write({'state': 'complete'})


class User(models.Model):
    _inherit = "res.users"

    name = fields.Char(string='姓名', required=True)
    department = fields.Many2one('leave.department', string='部门')
    user_rest = fields.Float(string='可调休天数', default=0.0, digits=(2, 1))
    user_year_rest = fields.Float(string='年假', default=3.0, digits=(2, 1))


class Department(models.Model):
    _name = 'leave.department'
    _description = '部门信息表'

    name = fields.Char('部门名称')


class Exam(models.Model):
    _name = 'leave.exam'
    _description = '审批人员'

    name = fields.Char('审批人员姓名')


